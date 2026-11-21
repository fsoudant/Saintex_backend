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
    #if DEBUG
    /// Dernière position vue, EN MÉMOIRE seulement (jamais écrite sur disque, cf. spec §7).
    private var dernierePositionVue: (latitude: Double, longitude: Double, date: Date)?
    #endif

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
        SejoursSelfTest.executer()
        // PROTOTYPE : séjours remis à zéro à chaque lancement en développement, pour pouvoir
        // rejouer un scénario (la première position dans la zone redonne une alerte d'entrée).
        store.etatsZones = [:]
        // PROTOTYPE : argument de lancement Xcode `-delaiSortieSecondes 300` (Edit Scheme > Run >
        // Arguments) pour rejouer le cas « retour après une longue absence » sans attendre 12 h.
        // Absent : délai réel de 12 h. L'auto-test séjours utilise toujours le délai réel.
        let delaiDebug = UserDefaults.standard.double(forKey: "delaiSortieSecondes")
        if delaiDebug > 0 {
            Sejours.delaiSortie = delaiDebug
            store.journal("DEBUG : délai de sortie réduit à \(Int(delaiDebug)) s (réel : 12 h)")
        }
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
            evaluerSiRecente(derniere, origine: "démarrage")
        }
        #if DEBUG
        // PROTOTYPE : en développement, contact forcé à chaque lancement pour récupérer le
        // cache à jour (sinon le cycle de 6 h retarde une zone de test fraîchement créée).
        contacterSiNecessaire(motif: "démarrage", force: true)
        #else
        contacterSiNecessaire(motif: "démarrage")
        #endif
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
        #if DEBUG
        // PROTOTYPE : le service à changement significatif ne livre pas de façon fiable les
        // positions simulées par Xcode (déplacements < ~500 m ignorés, au plus une mise à jour
        // toutes les ~5 min) : le suivi continu les reçoit toutes, y compris en arrière-plan
        // (mode « location » déclaré dans Info.plist). Build Debug uniquement.
        gestionnaire.allowsBackgroundLocationUpdates = true
        gestionnaire.startUpdatingLocation()
        store.journal("DEBUG : suivi continu de la position démarré")
        #endif
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
        #if DEBUG
        // Le suivi continu (Debug) redonne la même position simulée environ chaque seconde, ce qui
        // noie le journal (qui se tronque au-delà de 256 Ko) : une position identique à la
        // précédente, vue il y a moins de 5 min, n'est ni journalisée ni réévaluée.
        if let vue = dernierePositionVue,
           vue.latitude == position.coordinate.latitude,
           vue.longitude == position.coordinate.longitude,
           Date().timeIntervalSince(vue.date) < 300 {
            return
        }
        dernierePositionVue = (position.coordinate.latitude, position.coordinate.longitude, Date())
        #endif
        let age = Int(Date().timeIntervalSince(position.timestamp))
        // Aucune coordonnée dans le journal.
        store.journal("Position reçue (précision ± \(Int(position.horizontalAccuracy)) m, âgée de \(age) s, appli : \(etatApplication()))")
        evaluerSiRecente(position, origine: "changement de position")
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
            evaluerSiRecente(derniere, origine: "BGAppRefresh")
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

    /// Au-delà, une position n'est plus considérée comme « où je suis » : iOS livre au
    /// démarrage la dernière position CONNUE, parfois vieille de plusieurs jours, et alerter
    /// pour un lieu quitté depuis serait une fausse alerte.
    private let ageMaxPosition: TimeInterval = 30 * 60
    private var derniereDemandeDePosition: Date?

    /// N'évalue que les positions récentes ; pour une position trop vieille, en demande une
    /// fraîche (le résultat arrive par `didUpdateLocations`, qui réévalue). Au plus une
    /// demande par minute, pour ne pas boucler si le système renvoie encore une vieille position.
    private func evaluerSiRecente(_ position: CLLocation, origine: String) {
        let age = Date().timeIntervalSince(position.timestamp)
        if age <= ageMaxPosition {
            evaluer(position, origine: origine)
            return
        }
        store.journal("Position ignorée (\(origine)) : âgée de \(Int(age / 60)) min, nouvelle position demandée")
        let maintenant = Date()
        if let derniere = derniereDemandeDePosition, maintenant.timeIntervalSince(derniere) < 60 { return }
        derniereDemandeDePosition = maintenant
        gestionnaire.requestLocation()
    }

    private func evaluer(_ position: CLLocation, origine: String) {
        guard let cache = store.cache else {
            store.journal("Détection impossible (\(origine)) : pas encore de cache")
            return
        }
        let maintenant = Date()
        guard contratActif(maintenant) else {
            store.journal("Contrat non actif : silence")
            store.publierZonesAffichees(ZonesAffichees(
                misAJourLe: DatesISO.texte(maintenant), contratActif: false, risques: [], conseils: [:]
            ))
            retirerRappelsProgrammes()
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
        // Anti-répétition : cf. Sejours.swift (une oscillation de position autour d'un bord
        // de zone ne réalerte pas).
        let resultat = Sejours.evaluer(
            actives: actives,
            etats: store.etatsZones,
            maintenant: maintenant
        )
        store.etatsZones = resultat.etats
        publierZonesActuelles(actives: actives, cache: cache, maintenant: maintenant)
        store.journal("Détection (\(origine)) : \(actives.count) endémie(s) active(s), \(resultat.entrees.count) entrée(s)")
        if !resultat.entrees.isEmpty {
            alerter(entrees: resultat.entrees, cache: cache, instant: maintenant)
            // Remonter les rapports sans attendre le cycle de 6 h.
            contacterSiNecessaire(motif: "alerte affichée")
        }
        planifierRappels(cache: cache, etats: resultat.etats, maintenant: maintenant)
    }

    /// Titre et texte d'une alerte pour un risque (la phrase d'alerte du risque, suivie de la
    /// modulation de la première endémie concernée quand elle en a une).
    private func contenuAlerte(risque: CacheRisque, endemie: CacheEndemie, cache: CacheMondial) -> (libelle: String, corps: String) {
        let libelle = enFrancais ? risque.libelleFr : risque.libelleEn
        var corps = enFrancais ? risque.alerteFr : risque.alerteEn
        if let cleModulation = endemie.modulation, let modulation = cache.modulations[cleModulation] {
            let phrase = (enFrancais ? modulation.fr : modulation.en).trimmingCharacters(in: .whitespacesAndNewlines)
            if !phrase.isEmpty { corps += " " + phrase }
        }
        return (libelle, corps)
    }

    /// Une notification d'ENTRÉE par RISQUE concerné (plusieurs endémies du même risque sur la
    /// même position ne font qu'une alerte), et un rapport par notification affichée.
    private func alerter(entrees: [Int], cache: CacheMondial, instant: Date) {
        let ids = Set(entrees)
        let concernees = cache.endemies.filter { ids.contains($0.id) }
        let parRisque = Dictionary(grouping: concernees, by: { $0.risque })

        for (code, endemies) in parRisque.sorted(by: { $0.key < $1.key }) {
            guard let risque = cache.risques[code] else { continue }
            let endemies = endemies.sorted { $0.id < $1.id }
            let premiere = endemies[0]
            let contenu = contenuAlerte(risque: risque, endemie: premiere, cache: cache)

            poster(
                titre: (enFrancais ? "Zone à risque : " : "Risk area: ") + contenu.libelle,
                corps: contenu.corps,
                identifiant: "saintex.entree.\(code).\(Int(instant.timeIntervalSince1970))",
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

    // MARK: - Synthèse pour l'écran d'accueil

    /// À l'ouverture de l'appli : demande une position fraîche pour que l'accueil reflète l'endroit
    /// où se trouve le voyageur à cet instant (la réponse arrive par `didUpdateLocations`, qui
    /// réévalue et republie la synthèse).
    func actualiserPosition() {
        let statut = statutLocalisation
        guard statut == .authorizedAlways || statut == .authorizedWhenInUse else { return }
        gestionnaire.requestLocation()
    }

    /// Publie, pour l'accueil de la coque Capacitor, les risques présents à la position
    /// actuelle avec leurs recommandations (un seul bloc par risque, même si plusieurs endémies
    /// le portent). Aucune coordonnée : la synthèse ne contient que les noms des zones et les
    /// textes du cache.
    private func publierZonesActuelles(actives: Set<Int>, cache: CacheMondial, maintenant: Date) {
        let concernees = cache.endemies.filter { actives.contains($0.id) }
        let parRisque = Dictionary(grouping: concernees, by: { $0.risque })

        var risques: [RisqueAffiche] = []
        for (code, endemies) in parRisque.sorted(by: { $0.key < $1.key }) {
            guard let risque = cache.risques[code] else { continue }
            var phrasesFr: [String] = []
            var phrasesEn: [String] = []
            for endemie in endemies.sorted(by: { $0.id < $1.id }) {
                guard let cle = endemie.modulation, let modulation = cache.modulations[cle] else { continue }
                let fr = modulation.fr.trimmingCharacters(in: .whitespacesAndNewlines)
                let en = modulation.en.trimmingCharacters(in: .whitespacesAndNewlines)
                if !fr.isEmpty && !phrasesFr.contains(fr) { phrasesFr.append(fr) }
                if !en.isEmpty && !phrasesEn.contains(en) { phrasesEn.append(en) }
            }
            risques.append(RisqueAffiche(
                code: code,
                zones: Array(Set(endemies.map { $0.zoneNom })).sorted(),
                modulationFr: phrasesFr.isEmpty ? nil : phrasesFr.joined(separator: " "),
                modulationEn: phrasesEn.isEmpty ? nil : phrasesEn.joined(separator: " "),
                risque: risque
            ))
        }
        // Fiches conseil visées par les recommandations affichées : elles voyagent avec la synthèse,
        // pour que l'accueil les ouvre hors connexion.
        var conseils: [String: CacheConseil] = [:]
        if let toutes = cache.conseils {
            for entree in risques {
                for texte in [entree.risque.recommandationFr, entree.risque.recommandationEn] {
                    for code in CodesConseils.extraire(texte) {
                        if let conseil = toutes[code] { conseils[code] = conseil }
                    }
                }
            }
        }
        store.publierZonesAffichees(ZonesAffichees(
            misAJourLe: DatesISO.texte(maintenant), contratActif: true, risques: risques, conseils: conseils
        ))
    }

    // MARK: - Rappels programmés

    private static let prefixeRappel = "saintex.rappel."
    private let maxRappelsParRisque = 20
    /// iOS ne garde que 64 notifications locales en attente par appli : on reste en dessous.
    private let maxRappelsEnAttente = 60

    /// Programme les rappels d'un séjour prolongé comme notifications LOCALES à date fixe : un
    /// voyageur immobile ne réveille jamais l'appli, qui ne pourrait pas les afficher au fil
    /// de l'eau. Appelée à chaque évaluation ; remplace tous les rappels en attente :
    /// - un séjour dont on a vu la sortie n'a plus de rappel (il reprendra si l'on revient
    ///   avant la fin de `Sejours.delaiSortie`) ;
    /// - un changement de délai de rappel ou de cache se répercute ici.
    /// Ces rappels ne sont pas rapportés au serveur : iOS ne dit pas si, ni quand, ils ont
    /// été affichés.
    private func planifierRappels(cache: CacheMondial, etats: [Int: EtatZone], maintenant: Date) {
        let delai = store.delaiRappel
        let calendrier = Calendar.current
        let dedans = cache.endemies.filter { etats[$0.id].map { $0.sortieVueLe == nil } ?? false }
        let parRisque = Dictionary(grouping: dedans, by: { $0.risque })

        var demandes: [(date: Date, requete: UNNotificationRequest)] = []
        for (code, endemies) in parRisque {
            guard let risque = cache.risques[code] else { continue }
            let endemies = endemies.sorted { $0.id < $1.id }
            guard let entree = endemies.compactMap({ etats[$0.id]?.entreeLe }).min() else { continue }
            let dates = Sejours.datesDeRappel(
                entreeLe: entree, maintenant: maintenant, delai: delai,
                calendrier: calendrier, nombre: maxRappelsParRisque
            )
            let texte = contenuAlerte(risque: risque, endemie: endemies[0], cache: cache)
            for date in dates {
                let contenu = UNMutableNotificationContent()
                contenu.title = (enFrancais ? "Rappel — zone à risque : " : "Reminder — risk area: ") + texte.libelle
                contenu.body = texte.corps
                contenu.sound = .default
                contenu.userInfo = ["endemies": endemies.map { $0.id }]
                let composants = calendrier.dateComponents([.year, .month, .day, .hour, .minute, .second], from: date)
                let declencheur = UNCalendarNotificationTrigger(dateMatching: composants, repeats: false)
                let identifiant = "\(SaintexService.prefixeRappel)\(code).\(Int(date.timeIntervalSince1970))"
                demandes.append((date, UNNotificationRequest(identifier: identifiant, content: contenu, trigger: declencheur)))
            }
        }
        let retenues = demandes.sorted { $0.date < $1.date }.prefix(maxRappelsEnAttente)
        remplacerRappelsProgrammes(par: Array(retenues))
    }

    /// Supprime tous les rappels en attente (contrat devenu inactif, par exemple).
    private func retirerRappelsProgrammes() {
        remplacerRappelsProgrammes(par: [])
    }

    private func remplacerRappelsProgrammes(par demandes: [(date: Date, requete: UNNotificationRequest)]) {
        let centre = UNUserNotificationCenter.current()
        centre.getPendingNotificationRequests { enAttente in
            let anciens = enAttente.map { $0.identifier }.filter { $0.hasPrefix(SaintexService.prefixeRappel) }
            centre.removePendingNotificationRequests(withIdentifiers: anciens)
            for demande in demandes {
                centre.add(demande.requete) { erreur in
                    if let erreur = erreur {
                        DispatchQueue.main.async {
                            self.store.journal("Rappel non programmé : \(erreur.localizedDescription)")
                        }
                    }
                }
            }
            if !anciens.isEmpty || !demandes.isEmpty {
                DispatchQueue.main.async {
                    let prochain = demandes.first.map { DatesISO.texte($0.date) } ?? "aucun"
                    self.store.journal("Rappels programmés : \(demandes.count) (prochain : \(prochain))")
                }
            }
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
        if let preferences = reponse.preferences, let delai = DelaiRappel(rawValue: preferences.reminderDelay) {
            store.delaiRappel = delai
        }

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
            evaluerSiRecente(derniere, origine: "après contact")
        }
    }
}

/// Affiche aussi les alertes quand l'appli est au PREMIER PLAN. Sans cela, le routeur de
/// notifications de Capacitor (qui n'a ici aucun gestionnaire de notifications locales) répond
/// « ne rien afficher » à iOS : une alerte reçue pendant que le voyageur a l'appli ouverte
/// serait invisible, même dans le centre de notifications. Installé par
/// `AppDelegate.applicationDidBecomeActive`, une fois la coque Capacitor chargée (qui
/// s'attribue le rôle de délégué au chargement). iOS ne garde qu'une référence faible au
/// délégué : l'instance partagée le maintient en vie.
final class SaintexNotificationDelegate: NSObject, UNUserNotificationCenterDelegate {
    static let shared = SaintexNotificationDelegate()

    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        willPresent notification: UNNotification,
        withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void
    ) {
        if #available(iOS 14.0, *) {
            completionHandler([.banner, .list, .sound])
        } else {
            completionHandler([.alert, .sound])
        }
    }
}
