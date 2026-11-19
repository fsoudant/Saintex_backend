import Foundation

// Séjours en zone à risque : décide, pour chaque position, quelles ENTRÉES signaler, en
// évitant de réalerter en boucle quand la position oscille autour d'un bord de zone ; et
// calcule les dates des RAPPELS d'un séjour prolongé. Logique PURE (aucun accès au
// système) : DEBUG rejoue des scénarios dessus au démarrage (SejoursSelfTest).
//
// Le problème des oscillations : les positions utiles ont une incertitude de 1 à 2 km
// (antenne relais, service à changement significatif). Près d'une frontière de zone, deux
// positions successives peuvent tomber dedans, dehors, dedans... Compter chaque retour
// comme une nouvelle entrée enverrait une alerte à chaque oscillation.
//
// Règles d'entrée :
// - Une zone n'est « quittée » que si l'on est resté dehors au moins `delaiSortie` : un
//   retour plus rapide poursuit le MÊME séjour, sans nouvelle alerte d'entrée. L'absence se
//   mesure entre la première position vue dehors et le retour dedans.
// - Au-delà de `delaiSortie` dehors, un retour est une NOUVELLE entrée : nouvelle alerte.
//
// Rappels (séjour prolongé, selon `reminder_delay` choisi par le voyageur) : ils ne
// peuvent pas être évalués au réveil de l'appli — un voyageur immobile ne la réveille
// jamais. Ils sont donc PROGRAMMÉS à l'avance comme notifications locales (cf.
// SaintexService.planifierRappels), à une heure fixe de la journée pour ne réveiller
// personne la nuit, et reprogrammés à chaque évaluation.

enum DelaiRappel: String {
    case uneFois = "once"
    case quotidien = "daily"
    case tousLesDeuxJours = "every_2_days"
    case hebdomadaire = "weekly"

    /// Même valeur par défaut que le serveur (Utilisateur.reminder_delay).
    static let defaut = DelaiRappel.quotidien

    /// Nombre de jours entre deux rappels ; nil = jamais de rappel.
    var pasEnJours: Int? {
        switch self {
        case .uneFois: return nil
        case .quotidien: return 1
        case .tousLesDeuxJours: return 2
        case .hebdomadaire: return 7
        }
    }
}

/// État d'un séjour en cours dans une endémie (persisté entre deux réveils de l'appli).
struct EtatZone: Codable, Equatable {
    /// Début du séjour courant (dernière alerte d'entrée) : les rappels s'en déduisent.
    var entreeLe: Date
    /// Première position vue HORS de la zone depuis la dernière fois dedans ; nil tant
    /// qu'on est dedans.
    var sortieVueLe: Date?
}

enum Sejours {
    /// Durée dehors au-delà de laquelle un retour compte comme une nouvelle entrée.
    /// 12 h : un aller-retour dans la journée, ou une oscillation de GPS, n'est pas une
    /// nouvelle entrée ; une nuit passée hors de la zone, si.
    static let delaiSortie: TimeInterval = 12 * 3600

    /// Heure locale (de 0 à 23) des rappels : en matinée, jamais en pleine nuit.
    static let heureRappel = 9

    /// - Parameters:
    ///   - actives: endémies dont la zone contient la position actuelle.
    ///   - etats: séjours en cours (résultat de l'appel précédent).
    /// - Returns: les endémies où l'on vient d'ENTRER (à signaler, par ordre croissant
    ///   d'identifiant) et le nouvel état à conserver.
    static func evaluer(
        actives: Set<Int>,
        etats: [Int: EtatZone],
        maintenant: Date
    ) -> (entrees: [Int], etats: [Int: EtatZone]) {
        var nouveaux = etats
        var entrees: [Int] = []

        for id in actives.sorted() {
            guard var etat = etats[id] else {
                nouveaux[id] = EtatZone(entreeLe: maintenant, sortieVueLe: nil)
                entrees.append(id)
                continue
            }
            if let sortie = etat.sortieVueLe {
                if maintenant.timeIntervalSince(sortie) >= delaiSortie {
                    nouveaux[id] = EtatZone(entreeLe: maintenant, sortieVueLe: nil)
                    entrees.append(id)
                    continue
                }
                etat.sortieVueLe = nil  // retour rapide : même séjour
                nouveaux[id] = etat
            }
        }

        for (id, etat) in etats where !actives.contains(id) {
            if let sortie = etat.sortieVueLe {
                // Resté dehors assez longtemps : le séjour est clos (un retour sera une entrée).
                if maintenant.timeIntervalSince(sortie) >= delaiSortie { nouveaux[id] = nil }
            } else {
                var sorti = etat
                sorti.sortieVueLe = maintenant
                nouveaux[id] = sorti
            }
        }
        return (entrees, nouveaux)
    }

    /// Dates des prochains rappels d'un séjour commencé à `entreeLe` : tous les `pas`
    /// jours après le jour d'entrée, à `heureRappel` heures (heure du `calendrier`),
    /// uniquement celles qui sont encore à venir. Vide si le voyageur ne veut aucun rappel.
    static func datesDeRappel(
        entreeLe: Date,
        maintenant: Date,
        delai: DelaiRappel,
        calendrier: Calendar,
        nombre: Int
    ) -> [Date] {
        guard let pas = delai.pasEnJours, nombre > 0 else { return [] }
        let debutDuJour = calendrier.startOfDay(for: entreeLe)
        var dates: [Date] = []
        var k = 1
        while dates.count < nombre && k < 20_000 {
            if let jour = calendrier.date(byAdding: .day, value: k * pas, to: debutDuJour),
               let rappel = calendrier.date(bySettingHour: heureRappel, minute: 0, second: 0, of: jour),
               rappel > maintenant {
                dates.append(rappel)
            }
            k += 1
        }
        return dates
    }
}
