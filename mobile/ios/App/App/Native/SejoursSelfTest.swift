#if DEBUG
import Foundation

/// Rejoue des scénarios sur la logique des séjours (Sejours.swift) et écrit le verdict
/// dans le journal : « Auto-test séjours : N/N OK ». Build Debug uniquement.
enum SejoursSelfTest {
    private static let t0 = Date(timeIntervalSince1970: 1_800_000_000)

    private static func h(_ heures: Double) -> Date { t0.addingTimeInterval(heures * 3600) }

    /// Rejoue une série d'observations (heure, endémies actives) et renvoie les
    /// décisions de chaque étape.
    private static func rejouer(
        _ observations: [(Double, Set<Int>)],
        delai: DelaiRappel = .quotidien
    ) -> [[DecisionAlerte]] {
        var etats: [Int: EtatZone] = [:]
        var resultat: [[DecisionAlerte]] = []
        for (heures, actives) in observations {
            let sortie = Sejours.evaluer(actives: actives, etats: etats, maintenant: h(heures), delaiRappel: delai)
            etats = sortie.etats
            resultat.append(sortie.decisions)
        }
        return resultat
    }

    private static func entree(_ id: Int) -> DecisionAlerte { DecisionAlerte(endemie: id, type: .entree) }
    private static func rappel(_ id: Int) -> DecisionAlerte { DecisionAlerte(endemie: id, type: .rappel) }

    static func executer() {
        let store = SaintexStore.shared
        var echecs = 0
        var total = 0

        func verifier(_ nom: String, _ obtenu: [[DecisionAlerte]], _ attendu: [[DecisionAlerte]]) {
            total += 1
            if obtenu != attendu {
                echecs += 1
                store.journal("  ÉCHEC séjours « \(nom) » : attendu \(attendu), obtenu \(obtenu)")
            }
        }

        // Première entrée : une alerte, puis plus rien tant que le délai de rappel n'est pas échu.
        verifier("entrée puis silence",
                 rejouer([(0, [1]), (1, [1]), (5, [1])]),
                 [[entree(1)], [], []])

        // Oscillation autour d'un bord : dehors 10 min puis de nouveau dedans = même séjour.
        verifier("oscillation de bord",
                 rejouer([(0, [1]), (0.17, []), (0.33, [1]), (0.5, []), (0.67, [1])]),
                 [[entree(1)], [], [], [], []])

        // Dehors plus de 12 h : le retour est une nouvelle entrée (première position dehors à 1 h,
        // retour à 14 h, soit 13 h plus tard).
        verifier("retour après plus de 12 h",
                 rejouer([(0, [1]), (1, []), (14, [1])]),
                 [[entree(1)], [], [entree(1)]])

        // Dehors moins de 12 h : même séjour (1 h → 12 h = 11 h dehors).
        verifier("retour avant 12 h",
                 rejouer([(0, [1]), (1, []), (12, [1])]),
                 [[entree(1)], [], []])

        // Séjour clos par une observation dehors tardive, puis retour : nouvelle entrée.
        verifier("séjour clos puis nouvelle entrée",
                 rejouer([(0, [1]), (1, []), (14, []), (15, [1])]),
                 [[entree(1)], [], [], [entree(1)]])

        // Rappels quotidiens : un par jour passé dans la zone, mesurés depuis le dernier.
        verifier("rappels quotidiens",
                 rejouer([(0, [1]), (23, [1]), (25, [1]), (26, [1]), (50, [1]), (73, [1])]),
                 [[entree(1)], [], [rappel(1)], [], [rappel(1)], []])

        // « Une fois » : aucun rappel, même après des semaines.
        verifier("une fois, jamais de rappel",
                 rejouer([(0, [1]), (24 * 30, [1])], delai: .uneFois),
                 [[entree(1)], []])

        // Tous les 2 jours / hebdomadaire.
        verifier("tous les deux jours",
                 rejouer([(0, [1]), (47, [1]), (49, [1])], delai: .tousLesDeuxJours),
                 [[entree(1)], [], [rappel(1)]])
        verifier("hebdomadaire",
                 rejouer([(0, [1]), (24 * 6, [1]), (24 * 7 + 1, [1])], delai: .hebdomadaire),
                 [[entree(1)], [], [rappel(1)]])

        // Un retour rapide ne remet pas à zéro le compte à rebours du rappel.
        verifier("le rappel survit à une oscillation",
                 rejouer([(0, [1]), (20, []), (21, [1]), (25, [1])]),
                 [[entree(1)], [], [], [rappel(1)]])

        // Plusieurs endémies : suivies indépendamment.
        verifier("endémies indépendantes",
                 rejouer([(0, [1]), (1, [1, 2]), (2, [2])]),
                 [[entree(1)], [entree(2)], []])

        // Entrée simultanée dans deux endémies : une décision chacune, dans l'ordre des identifiants.
        verifier("entrées simultanées",
                 rejouer([(0, [5, 3])]),
                 [[entree(3), entree(5)]])

        store.journal("Auto-test séjours : \(total - echecs)/\(total) OK" + (echecs == 0 ? " ✅" : " ❌"))
    }
}
#endif
