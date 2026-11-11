import UIKit
import CoreLocation
import BackgroundTasks
import UserNotifications

/// Cœur natif de Saintex (PROTOTYPE d'essai iOS) : tâche de fond qui détecte
/// l'entrée en zone à risque à partir du cache fourni par le serveur et affiche
/// une notification LOCALE, puis rapporte l'alerte au serveur (spec §4, §5, §8).
///
/// Mécanismes de réveil testés :
/// - service de localisation à changement significatif : relance l'appli après
///   un déplacement notable, même terminée par le système ou après un
///   redémarrage (mais plus si l'utilisateur l'a quittée de force) ;
/// - BGAppRefreshTask : réveil opportuniste, iOS décide du moment réel.
///
/// Tout s'exécute sur le thread principal (délégués CoreLocation, handlers
/// ramenés sur `DispatchQueue.main`).
final class SaintexService: NSObject, CLLocationManagerDelegate {
    static let shared = SaintexService()

    static let identifiantRafraichissement = "com.saintex.app.refresh"

    private let gestionnaire = CLLocationManager()
    private let store = SaintexStore.shared
    private let serveur = SaintexServer()

    private var detecteur: Detecteur?
    private var contactEnCours = false
    private var contactSupplementaireDemande = false
    private var dernierJetonConnu: String?

    /// Cycle de contact visé (spec §4) et marge : un réveil un peu en avance
    /// ne doit pas faire sauter un contact.
    private let intervalleContact: TimeInterval = 6 * 3600
    private let margeContact: TimeInterval = 15 * 60

    private var enFrancais: Bool {
        return Locale.preferredLanguages.first?.hasPrefix("fr") ?? true
    }

    private var statutLocalisation: CLAuthorizationStatus {
        if #available(iOS 14.0, *) {
            return gestionnaire.authorizationStatus
        }
        return CLLocationManager.authorizationStatus()
    }

    // MARK: - Démarrage

    /// À appeler depuis `application(_:didFinishLaunchingWithOptions:)`, y
    /// compris lorsque l'appli est relancée en arrière-plan par le système :
    /// le gestionnaire de localisation et son délégué doivent exister dès le
    /// lancement pour recevoir les positions.
    func demarrer() {
        store.journal("— Démarrage du module natif (état appli : \(etatApplication()))")
        dernierJetonConnu = store.apiToken

        #if DEBUG
        DetectionSelfTest.executer()
        #endif

        gestionnaire.delegate = self
        gestionnaire.desiredAccuracy = kCLLocationAccuracyKilometer
        gestionnaire.pausesLocationUpdatesAutomatically = false

        enregistrerTacheRafraichissement()
        demanderAutorisations()
        demarrerSurveillance()
        planifierRafraichissement()

        NotificationCenter.default.addObserver(
            forName: UserDefaults.didChangeNotification, object: nil, queue: .main
        ) { [weak self] _ in self?.jetonPeutAvoirChange() }

        // Détection immédiate avec le cache déjà détenu (fonctionne hors ligne),
        // puis contact si le cycle est échu.
        if let derniere = gestionnaire.location {
            evaluer(derniere, origine: "démarrage")
        }
        contacterSiNecessaire(motif: "démarrage")
    }

    private func etatApplication() -> String {
        switch UIApplication.shared.applicationState {
        case .active: return "active"
        case .inactive: return "inactive"
        case .background: return "arrière-plan"
        @unknown default: return "inconnu"
        }
    }

    private func demanderAutorisations() {
        switch statutLocalisation {
        case .notDetermined:
            gestionnaire.requestWhenInUseAuthorization()
        case .authorizedWhenInUse:
            // iOS impose de passer par « Lorsque l'app est active » avant de
            // proposer « Toujours ».
            gestionnaire.requestAlwaysAuthorization()
        default:
            break
        }
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound]) { accordee, _ in
            DispatchQueue.main.async {
                self.store.journal("Autorisation de notifications : \(accordee ? "accordée" : "refusée")")
            }
        }
    }

    private func demarrerSurveillance() {
        let statut = statutLocalisation
        guard statut == .authorizedAlways || statut == .authorizedWhenInUse else {
            store.journal("Surveillance non démarrée : localisation non autorisée")
            return
        }
        if CLLocationManager.significantLocationChangeMonitoringAvailable() {
            gestionnaire.startMonitoringSignificantLocationChanges()
            store.journal("Localisation à changement significatif démarrée (statut : \(libelle(statut)))")
        } else {
            store.journal("Localisation à changement significatif indisponible sur cet appareil")
        }
    }

    private func libelle(_ statut: CLAuthorizationStatus) -> String {
        switch statut {
        case .notDetermined: return "non déterminé"
        case .restricted: return "restreint"
        case .denied: return "refusé"
        case .authorizedAlways: return "toujours"
        case .authorizedWhenInUse: return "pendant l'utilisation"
        @unknown default: return "inconnu"
        }
    }

    // MARK: - Délégué CoreLocation

    func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        guard let position = locations.last else { return }
        let age = Int(Date().timeIntervalSince(position.timestamp))
        // Aucune coordonnée dans le journal.
        store.journal("Position reçue (précision ± \(Int(position.horizontalAccuracy)) m, âgée de \(age) s, appli : \(etatApplication()))")
        evaluer(position, origine: "changement de position")
        contacterSiNecessaire(motif: "changement de position")
    }

    func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {
        store.journal("Erreur de localisation : \(error.localizedDescription)")
    }

    @available(iOS 14.0, *)
    func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) {
        autorisationChangee()
    }

    func locationManager(_ manager: CLLocationManager, didChangeAuthorization status: CLAuthorizationStatus) {
        if #available(iOS 14.0, *) { return }  // géré par locationManagerDidChangeAuthorization
        autorisationChangee()
    }

    private func autorisationChangee() {
        var complement = ""
        if #available(iOS 14.0, *), gestionnaire.accuracyAuthorization == .reducedAccuracy {
            complement = " — ATTENTION : position approximative (précision réduite)"
        }
        store.journal("Autorisation de localisation : \(libelle(statutLocalisation))\(complement)")
        if statutLocalisation == .authorizedWhenInUse {
            gestionnaire.requestAlwaysAuthorization()
        }
        demarrerSurveillance()
    }

    // MARK: - Réveil opportuniste (BGAppRefreshTask)

    private func enregistrerTacheRafraichissement() {
        BGTaskScheduler.shared.register(forTaskWithIdentifier: SaintexService.identifiantRafraichissement, using: nil) { tache in
            DispatchQueue.main.async {
                guard let tache = tache as? BGAppRefreshTask else { return }
                self.traiterRafraichissement(tache)
            }
        }
    }

    private func planifierRafraichissement() {
        let demande = BGAppRefreshTaskRequest(identifier: SaintexService.identifiantRafraichissement)
        demande.earliestBeginDate = Date(timeIntervalSinceNow: intervalleContact)
        do {
            try BGTaskScheduler.shared.submit(demande)
        } catch {
            store.journal("Planification du réveil impossible : \(error.localizedDescription)")
        }
    }

    private func traiterRafraichissement(_ tache: BGAppRefreshTask) {
        planifierRafraichissement()
        store.journal("Réveil par BGAppRefresh")

        var termine = false
        let finir: (Bool) -> Void = { succes in
            DispatchQueue.main.async {
                if !termine {
                    termine = true
                    tache.setTaskCompleted(success: succes)
                }
            }
        }
        tache.expirationHandler = {
            self.store.journal("Réveil BGAppRefresh interrompu par le système")
            finir(false)
        }

        // Dernière position connue (mise à jour par le service de changement
        // significatif) ; on en demande aussi une fraîche, sans l'attendre.
        if let derniere = gestionnaire.location {
            evaluer(derniere, origine: "BGAppRefresh")
        } else {
            store.journal("Aucune position connue")
        }
        gestionnaire.requestLocation()
        contacterSiNecessaire(motif: "BGAppRefresh") { finir(true) }
    }

    // MARK: - Détection et alerte

    private func contratActif(_ maintenant: Date) -> Bool {
        #if DEBUG
        // PROTOTYPE : en build de développement, le contrat est ignoré pour
        // pouvoir tester sans date de début. Le build de production applique
        // la règle « muette avant le début et après l'expiration » (spec §6).
        return true
        #else
        guard let contrat = store.contrat,
              let texteDebut = contrat.debut,
              let debut = jour(texteDebut), maintenant >= debut else { return false }
        // À confirmer : la date d'expiration est-elle incluse ? Ici, active
        // jusqu'à la fin de ce jour.
        if let texteFin = contrat.expiration, let fin = jour(texteFin),
           let finDeJournee = Calendar.current.date(byAdding: .day, value: 1, to: fin),
           maintenant >= finDeJournee { return false }
        return true
        #endif
    }

    private func jour(_ texte: String) -> Date? {
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.timeZone = .current
        f.dateFormat = "yyyy-MM-dd"
        return f.date(from: texte)
    }

    private func evaluer(_ position: CLLocation, origine: String) {
        guard let cache = store.cache else {
            store.journal("Détection impossible (\(origine)) : pas encore de cache")
            return
        }
        let maintenant = Date()
        guard contratActif(maintenant) else {
            store.journal("Contrat non actif : silence")
            return
        }
        if detecteur?.version != cache.version {
            detecteur = Detecteur(cache: cache)
        }
        guard let detecteur = detecteur else { return }

        let actives = Set(detecteur.endemiesActives(
            lon: position.coordinate.longitude,
            lat: position.coordinate.latitude,
            instant: maintenant
        ))
        let nouvelles = actives.subtracting(store.zonesActives)
        store.zonesActives = actives
        store.journal("Détection (\(origine)) : \(actives.count) endémie(s) active(s), \(nouvelles.count) nouvelle(s)")
        if !nouvelles.isEmpty {
            alerter(nouvelles, cache: cache, instant: maintenant)
            // Remonter les rapports sans attendre le cycle de 6 h.
            contacterSiNecessaire(motif: "alerte affichée")
        }
    }

    /// Une notification par RISQUE nouvellement détecté (plusieurs endémies du
    /// même risque sur la même position ne font qu'une alerte), et un rapport
    /// par notification affichée.
    private func alerter(_ ids: Set<Int>, cache: CacheMondial, instant: Date) {
        let nouvelles = cache.endemies.filter { ids.contains($0.id) }
        let parRisque = Dictionary(grouping: nouvelles, by: { $0.risque })

        for (code, endemies) in parRisque.sorted(by: { $0.key < $1.key }) {
            guard let risque = cache.risques[code] else { continue }
            let endemies = endemies.sorted { $0.id < $1.id }
            let premiere = endemies[0]

            let libelle = enFrancais ? risque.libelleFr : risque.libelleEn
            var corps = enFrancais ? risque.alerteFr : risque.alerteEn
            if let cleModulation = premiere.modulation, let modulation = cache.modulations[cleModulation] {
                let phrase = (enFrancais ? modulation.fr : modulation.en).trimmingCharacters(in: .whitespacesAndNewlines)
                if !phrase.isEmpty { corps += " " + phrase }
            }

            poster(
                titre: (enFrancais ? "Zone à risque : " : "Risk area: ") + libelle,
                corps: corps,
                identifiant: "saintex.alerte.\(code).\(Int(instant.timeIntervalSince1970))",
                infos: ["endemies": endemies.map { $0.id }]
            )
            store.journal("Alerte affichée : \(code), endémie \(premiere.id) (\(premiere.zoneNom))")

            store.ajouterRapport(RapportAlerte(
                id: UUID().uuidString.lowercased(),
                endemie: premiere.id,
                type: "entree",
                afficheeLe: DatesISO.texte(instant),
                cacheVersion: cache.version
            ))
        }
    }

    private func poster(titre: String, corps: String, identifiant: String, infos: [String: Any] = [:]) {
        let contenu = UNMutableNotificationContent()
        contenu.title = titre
        contenu.body = corps
        contenu.sound = .default
        contenu.userInfo = infos
        let demande = UNNotificationRequest(identifier: identifiant, content: contenu, trigger: nil)
        UNUserNotificationCenter.current().add(demande) { erreur in
            if let erreur = erreur {
                DispatchQueue.main.async {
                    self.store.journal("Notification locale refusée : \(erreur.localizedDescription)")
                }
            }
        }
    }

    // MARK: - Contact avec le serveur

    private func jetonPeutAvoirChange() {
        let jeton = store.apiToken
        guard jeton != dernierJetonConnu else { return }
        dernierJetonConnu = jeton
        if jeton != nil {
            store.journal("Jeton API détecté : contact immédiat")
            contacterSiNecessaire(motif: "nouveau jeton", force: true)
        }
    }

    /// Contacte le serveur si le cycle de 6 h est échu, si `force`, ou si des
    /// rapports d'alerte attendent d'être remontés : c'est la réception du rapport
    /// qui déclenche le SMS de sauvegarde côté serveur (spec §8), il ne doit pas
    /// attendre le prochain cycle. `fin` est toujours appelé, sur le thread
    /// principal.
    private func contacterSiNecessaire(motif: String, force: Bool = false, fin: @escaping () -> Void = {}) {
        guard !contactEnCours else {
            // Un contact est déjà parti : si un rapport est apparu entre-temps
            // (alerte détectée pendant ce contact), il repartira juste après.
            if force || !store.rapportsEnAttente.isEmpty { contactSupplementaireDemande = true }
            fin()
            return
        }
        guard let jeton = store.apiToken else {
            store.journal("Contact impossible (\(motif)) : pas de jeton API")
            fin()
            return
        }
        let maintenant = Date()
        if !force, store.rapportsEnAttente.isEmpty, let dernier = store.dernierContact,
           maintenant.timeIntervalSince(dernier) < intervalleContact - margeContact {
            fin()
            return
        }

        contactEnCours = true
        store.journal("Contact avec le serveur (\(motif))")

        // Laisse à l'appli le temps de terminer l'appel réseau si elle passe en
        // arrière-plan ou est sur le point d'être suspendue.
        var tacheArrierePlan = UIBackgroundTaskIdentifier.invalid
        func terminer() {
            contactEnCours = false
            if tacheArrierePlan != .invalid {
                UIApplication.shared.endBackgroundTask(tacheArrierePlan)
                tacheArrierePlan = .invalid
            }
            if contactSupplementaireDemande {
                contactSupplementaireDemande = false
                if !store.rapportsEnAttente.isEmpty {
                    contacterSiNecessaire(motif: "rapport en attente", force: true, fin: fin)
                    return
                }
            }
            fin()
        }
        tacheArrierePlan = UIApplication.shared.beginBackgroundTask(withName: "saintex.contact") {
            self.store.journal("Contact interrompu : temps d'arrière-plan épuisé")
            terminer()
        }

        UNUserNotificationCenter.current().getNotificationSettings { reglages in
            DispatchQueue.main.async {
                let autorisees = reglages.authorizationStatus == .authorized
                    || reglages.authorizationStatus == .provisional
                let requete = ContactRequest(
                    cacheVersion: self.store.cache?.version,
                    sante: SanteAppli(
                        localisationToujours: self.statutLocalisation == .authorizedAlways,
                        notificationsAutorisees: autorisees
                    ),
                    rapports: Array(self.store.rapportsEnAttente.prefix(100))
                )
                self.serveur.contacter(requete, jeton: jeton) { resultat in
                    DispatchQueue.main.async {
                        switch resultat {
                        case .success(let reponse):
                            self.appliquer(reponse)
                        case .failure(let erreur):
                            self.store.journal("Échec du contact : \(erreur)")
                        }
                        terminer()
                    }
                }
            }
        }
    }

    private func appliquer(_ reponse: ContactResponse) {
        store.dernierContact = Date()
        store.contrat = reponse.contrat
        store.retirerRapports(ids: reponse.rapportsRecus)

        var resume = "Contact réussi"
        switch reponse.cache {
        case .complet(let nouveau):
            store.enregistrerCache(nouveau)
            resume += " : nouveau cache v\(nouveau.version) (\(nouveau.endemies.count) endémies)"
        case .inchange(let version):
            resume += " : cache inchangé v\(version)"
        }
        resume += ", \(reponse.rapportsRecus.count) rapport(s) acquitté(s), \(store.rapportsEnAttente.count) en attente"
        store.journal(resume)

        // Le cache a pu changer : réévaluer avec la dernière position connue.
        if let derniere = gestionnaire.location {
            evaluer(derniere, origine: "après contact")
        }
    }
}
