import Foundation

/// Persistance locale du module natif : cache des zones, dates du contrat,
/// état de détection, file d'attente des rapports d'alerte, journal d'essai.
/// Tout est utilisé depuis le thread principal.
///
/// Aucune position n'est jamais écrite ici (spec §7 : minimisation maximale).
final class SaintexStore {
    static let shared = SaintexStore()

    private let defaults = UserDefaults.standard
    private let dossier: URL
    private let fichierCache: URL
    private let fichierJournal: URL

    private(set) var cache: CacheMondial?

    private enum Cle {
        // Même clé que la coque Capacitor : @capacitor/preferences écrit dans
        // UserDefaults.standard avec le préfixe "CapacitorStorage." (vérifié
        // dans node_modules/@capacitor/preferences/ios/.../Preferences.swift).
        static let jeton = "CapacitorStorage.saintex_api_token"
        static let dernierContact = "saintex.native.dernierContact"
        static let contratDebut = "saintex.native.contratDebut"
        static let contratExpiration = "saintex.native.contratExpiration"
        static let zonesActives = "saintex.native.zonesActives"
        static let rapports = "saintex.native.rapportsEnAttente"
    }

    private init() {
        let fm = FileManager.default
        let support = fm.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
        dossier = support.appendingPathComponent("Saintex", isDirectory: true)
        try? fm.createDirectory(at: dossier, withIntermediateDirectories: true)
        fichierCache = dossier.appendingPathComponent("cache.json")

        // Journal d'essai dans Documents : lisible depuis l'app Fichiers de
        // l'iPhone (UIFileSharingEnabled, cf. Info.plist) — PROTOTYPE.
        let documents = fm.urls(for: .documentDirectory, in: .userDomainMask)[0]
        fichierJournal = documents.appendingPathComponent("saintex-journal.txt")

        if let data = try? Data(contentsOf: fichierCache) {
            cache = try? JSONDecoder().decode(CacheMondial.self, from: data)
        }
    }

    // MARK: - Jeton, contrat, contact

    var apiToken: String? {
        let valeur = defaults.string(forKey: Cle.jeton)
        return (valeur?.isEmpty ?? true) ? nil : valeur
    }

    var dernierContact: Date? {
        get { defaults.object(forKey: Cle.dernierContact) as? Date }
        set { defaults.set(newValue, forKey: Cle.dernierContact) }
    }

    var contrat: ContratInfo? {
        get {
            let debut = defaults.string(forKey: Cle.contratDebut)
            let expiration = defaults.string(forKey: Cle.contratExpiration)
            if debut == nil && expiration == nil { return nil }
            return ContratInfo(debut: debut, expiration: expiration)
        }
        set {
            defaults.set(newValue?.debut, forKey: Cle.contratDebut)
            defaults.set(newValue?.expiration, forKey: Cle.contratExpiration)
        }
    }

    // MARK: - Cache

    func enregistrerCache(_ nouveau: CacheMondial) {
        cache = nouveau
        do {
            let data = try JSONEncoder().encode(nouveau)
            try data.write(to: fichierCache, options: [.atomic, .completeFileProtectionUntilFirstUserAuthentication])
        } catch {
            journal("Écriture du cache impossible : \(error.localizedDescription)")
        }
    }

    // MARK: - État de détection

    /// Identifiants des endémies actives au dernier calcul (pour ne signaler
    /// que les NOUVELLES entrées en zone).
    var zonesActives: Set<Int> {
        get { Set((defaults.array(forKey: Cle.zonesActives) as? [Int]) ?? []) }
        set { defaults.set(Array(newValue).sorted(), forKey: Cle.zonesActives) }
    }

    // MARK: - Rapports d'alerte en attente de remontée

    var rapportsEnAttente: [RapportAlerte] {
        get {
            guard let data = defaults.data(forKey: Cle.rapports) else { return [] }
            return (try? JSONDecoder().decode([RapportAlerte].self, from: data)) ?? []
        }
        set {
            defaults.set(try? JSONEncoder().encode(newValue), forKey: Cle.rapports)
        }
    }

    func ajouterRapport(_ rapport: RapportAlerte) {
        rapportsEnAttente = rapportsEnAttente + [rapport]
    }

    func retirerRapports(ids: [String]) {
        guard !ids.isEmpty else { return }
        let acquittes = Set(ids.map { $0.lowercased() })
        rapportsEnAttente = rapportsEnAttente.filter { !acquittes.contains($0.id.lowercased()) }
    }

    // MARK: - Journal d'essai (PROTOTYPE)

    private static let formatJournal: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd HH:mm:ss"
        return f
    }()

    /// Ajoute une ligne au journal. Ne JAMAIS y mettre de coordonnées.
    func journal(_ message: String) {
        let ligne = "\(SaintexStore.formatJournal.string(from: Date()))  \(message)\n"
        NSLog("[Saintex] %@", message)
        guard let data = ligne.data(using: .utf8) else { return }
        let fm = FileManager.default
        if fm.fileExists(atPath: fichierJournal.path) {
            if let handle = try? FileHandle(forWritingTo: fichierJournal) {
                handle.seekToEndOfFile()
                handle.write(data)
                try? handle.close()
            }
            if let taille = (try? fm.attributesOfItem(atPath: fichierJournal.path))?[.size] as? Int, taille > 256_000,
               let contenu = try? Data(contentsOf: fichierJournal) {
                try? contenu.suffix(128_000).write(to: fichierJournal, options: .atomic)
            }
        } else {
            try? data.write(to: fichierJournal, options: .atomic)
        }
    }
}
