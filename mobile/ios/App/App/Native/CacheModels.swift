import Foundation

// Modèles du cache hors ligne transmis par le serveur (POST /api/cache/).
// Format 2 : cf. docstring de risks/cache.py côté backend et
// tests_partages/detection_cache.json (même format, jeu de test partagé).
//
// ATTENTION : pas de `keyDecodingStrategy = .convertFromSnakeCase` — elle
// s'appliquerait aussi aux CLÉS des dictionnaires (codes de risques et de
// modulations comme "P_T3_A_SR") et casserait les références. D'où les
// CodingKeys explicites.

struct CacheSaison: Codable, Equatable {
    let debut: Int
    let fin: Int
}

struct CacheModulation: Codable {
    let fr: String
    let en: String
    let saison: CacheSaison?
}

struct CacheRisque: Codable {
    let libelleFr: String
    let libelleEn: String
    let couleur: String?
    let alerteFr: String
    let alerteEn: String
    let descriptionFr: String
    let descriptionEn: String
    let recommandationFr: String
    let recommandationEn: String

    enum CodingKeys: String, CodingKey {
        case libelleFr = "libelle_fr"
        case libelleEn = "libelle_en"
        case couleur
        case alerteFr = "alerte_fr"
        case alerteEn = "alerte_en"
        case descriptionFr = "description_fr"
        case descriptionEn = "description_en"
        case recommandationFr = "recommandation_fr"
        case recommandationEn = "recommandation_en"
    }
}

/// MultiPolygon GeoJSON : polygones → anneaux (le premier est l'extérieur, les
/// suivants sont des trous) → points [longitude, latitude].
struct CacheGeometrie: Codable {
    let type: String
    let coordinates: [[[[Double]]]]
}

struct CacheEndemie: Codable {
    let id: Int
    let zoneId: Int
    let zoneNom: String
    let risque: String
    let modulation: String?
    let geometrie: String
    let valideDu: String?
    let valideAu: String?

    enum CodingKeys: String, CodingKey {
        case id
        case zoneId = "zone_id"
        case zoneNom = "zone_nom"
        case risque
        case modulation
        case geometrie
        case valideDu = "valide_du"
        case valideAu = "valide_au"
    }
}

struct CacheMondial: Codable {
    let version: String
    let genereLe: String
    let format: Int
    let rayonKm: Double?
    let risques: [String: CacheRisque]
    let modulations: [String: CacheModulation]
    let geometries: [String: CacheGeometrie]
    let endemies: [CacheEndemie]

    enum CodingKeys: String, CodingKey {
        case version
        case genereLe = "genere_le"
        case format
        case rayonKm = "rayon_km"
        case risques
        case modulations
        case geometries
        case endemies
    }
}

// MARK: - Contact avec le serveur

struct ContratInfo: Codable {
    let debut: String?       // date ISO "AAAA-MM-JJ"
    let expiration: String?
}

struct SanteAppli: Codable {
    let localisationToujours: Bool
    let notificationsAutorisees: Bool

    enum CodingKeys: String, CodingKey {
        case localisationToujours = "localisation_toujours"
        case notificationsAutorisees = "notifications_autorisees"
    }
}

/// Rapport d'une alerte affichée par le téléphone (aucune coordonnée).
/// `id` : UUID généré par le téléphone, pour que le renvoi soit idempotent.
struct RapportAlerte: Codable {
    let id: String
    let endemie: Int
    let type: String          // "entree" | "rappel"
    let afficheeLe: String    // ISO 8601
    let cacheVersion: String?

    enum CodingKeys: String, CodingKey {
        case id
        case endemie
        case type
        case afficheeLe = "affichee_le"
        case cacheVersion = "cache_version"
    }
}

struct ContactRequest: Encodable {
    let cacheVersion: String?
    let sante: SanteAppli
    let rapports: [RapportAlerte]

    enum CodingKeys: String, CodingKey {
        case cacheVersion = "cache_version"
        case sante
        case rapports
    }
}

/// Le champ `cache` de la réponse : soit le cache complet, soit
/// `{"version": ..., "inchange": true}`.
enum CacheReponse: Decodable {
    case inchange(version: String)
    case complet(CacheMondial)

    private enum Cles: String, CodingKey {
        case version
        case inchange
    }

    init(from decoder: Decoder) throws {
        let conteneur = try decoder.container(keyedBy: Cles.self)
        if conteneur.contains(.inchange) {
            self = .inchange(version: try conteneur.decode(String.self, forKey: .version))
        } else {
            self = .complet(try CacheMondial(from: decoder))
        }
    }
}

/// Préférences que le téléphone applique lui-même (c'est lui qui affiche les alertes),
/// renvoyées à chaque contact. `reminderDelay` : once, daily, every_2_days, weekly.
struct PreferencesTelephone: Codable {
    let reminderDelay: String

    enum CodingKeys: String, CodingKey {
        case reminderDelay = "reminder_delay"
    }
}

struct ContactResponse: Decodable {
    let contrat: ContratInfo
    let cache: CacheReponse
    let rapportsRecus: [String]
    let preferences: PreferencesTelephone?

    enum CodingKeys: String, CodingKey {
        case contrat
        case cache
        case rapportsRecus = "rapports_recus"
        case preferences
    }
}
