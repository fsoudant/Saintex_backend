import Foundation

// Séjours en zone à risque : décide, pour chaque position, quelles alertes afficher
// (entrée) ou rappeler (séjour prolongé), en évitant de réalerter en boucle quand la
// position oscille autour d'un bord de zone. Logique PURE (aucun accès au système) :
// DEBUG rejoue des scénarios dessus au démarrage (SejoursSelfTest).
//
// Le problème : les positions utiles ont une incertitude de 1 à 2 km (antenne relais,
// service à changement significatif). Près d'une frontière de zone, deux positions
// successives peuvent tomber dedans, dehors, dedans... Compter chaque retour comme une
// nouvelle entrée enverrait une alerte à chaque oscillation.
//
// Règles :
// - Une zone n'est « quittée » que si l'on est resté dehors au moins `delaiSortie` :
//   un retour plus rapide poursuit le MÊME séjour, sans nouvelle alerte d'entrée.
//   L'absence se mesure entre la première position vue dehors et le retour dedans.
// - Au-delà de `delaiSortie` dehors, un retour est une NOUVELLE entrée : nouvelle alerte.
// - Pendant un séjour, un rappel est affiché tous les `intervalle` du délai choisi par le
//   voyageur (reminder_delay), mesuré depuis la dernière alerte ou le dernier rappel ;
//   « une fois » ne rappelle jamais.

enum DelaiRappel: String {
    case uneFois = "once"
    case quotidien = "daily"
    case tousLesDeuxJours = "every_2_days"
    case hebdomadaire = "weekly"

    /// Même valeur par défaut que le serveur (Utilisateur.reminder_delay).
    static let defaut = DelaiRappel.quotidien

    /// Intervalle entre deux rappels ; nil = jamais de rappel.
    var intervalle: TimeInterval? {
        switch self {
        case .uneFois: return nil
        case .quotidien: return 24 * 3600
        case .tousLesDeuxJours: return 48 * 3600
        case .hebdomadaire: return 7 * 24 * 3600
        }
    }
}

/// État d'un séjour en cours dans une endémie (persisté entre deux réveils de l'appli).
struct EtatZone: Codable, Equatable {
    /// Début du séjour courant (dernière alerte d'entrée).
    var entreeLe: Date
    /// Dernière alerte d'entrée ou dernier rappel affiché : base du prochain rappel.
    var derniereAlerteLe: Date
    /// Première position vue HORS de la zone depuis la dernière fois dedans ; nil tant
    /// qu'on est dedans.
    var sortieVueLe: Date?
}

enum TypeAlerte: String {
    case entree
    case rappel
}

struct DecisionAlerte: Equatable {
    let endemie: Int
    let type: TypeAlerte
}

enum Sejours {
    /// Durée dehors au-delà de laquelle un retour compte comme une nouvelle entrée.
    /// 12 h : un aller-retour dans la journée, ou une oscillation de GPS, n'est pas une
    /// nouvelle entrée ; une nuit passée hors de la zone, si.
    static let delaiSortie: TimeInterval = 12 * 3600

    /// - Parameters:
    ///   - actives: endémies dont la zone contient la position actuelle.
    ///   - etats: séjours en cours (résultat de l'appel précédent).
    /// - Returns: les alertes à afficher et le nouvel état à conserver.
    static func evaluer(
        actives: Set<Int>,
        etats: [Int: EtatZone],
        maintenant: Date,
        delaiRappel: DelaiRappel
    ) -> (decisions: [DecisionAlerte], etats: [Int: EtatZone]) {
        var nouveaux = etats
        var decisions: [DecisionAlerte] = []

        for id in actives.sorted() {
            guard var etat = etats[id] else {
                nouveaux[id] = EtatZone(entreeLe: maintenant, derniereAlerteLe: maintenant, sortieVueLe: nil)
                decisions.append(DecisionAlerte(endemie: id, type: .entree))
                continue
            }
            if let sortie = etat.sortieVueLe {
                if maintenant.timeIntervalSince(sortie) >= delaiSortie {
                    nouveaux[id] = EtatZone(entreeLe: maintenant, derniereAlerteLe: maintenant, sortieVueLe: nil)
                    decisions.append(DecisionAlerte(endemie: id, type: .entree))
                    continue
                }
                etat.sortieVueLe = nil  // retour rapide : même séjour
            }
            if let intervalle = delaiRappel.intervalle,
               maintenant.timeIntervalSince(etat.derniereAlerteLe) >= intervalle {
                etat.derniereAlerteLe = maintenant
                decisions.append(DecisionAlerte(endemie: id, type: .rappel))
            }
            nouveaux[id] = etat
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
        return (decisions, nouveaux)
    }
}
