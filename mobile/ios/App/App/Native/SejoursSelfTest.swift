#if DEBUG
import Foundation

/// Rejoue des scénarios sur la logique des séjours et des rappels (Sejours.swift) et écrit
/// le verdict dans le journal : « Auto-test séjours : N/N OK ». Build Debug uniquement.
enum SejoursSelfTest {
    private static let t0 = Date(timeIntervalSince1970: 1_800_000_000)

    private static func h(_ heures: Double) -> Date { t0.addingTimeInterval(heures * 3600) }

    /// Rejoue une série d'observations (heure, endémies actives) et renvoie, à chaque
    /// étape, les endémies où l'on vient d'entrer.
    private static func rejouer(_ observations: [(Double, Set<Int>)]) -> [[Int]] {
        var etats: [Int: EtatZone] = [:]
        var resultat: [[Int]] = []
        for (heures, actives) in observations {
            let sortie = Sejours.evaluer(actives: actives, etats: etats, maintenant: h(heures))
            etats = sortie.etats
            resultat.append(sortie.entrees)
        }
        return resultat
    }

    private static let utc: Calendar = {
        var calendrier = Calendar(identifier: .gregorian)
        calendrier.timeZone = TimeZone(identifier: "UTC")!
        return calendrier
    }()

    private static func date(_ jour: Int, _ heure: Int, _ minute: Int = 0) -> Date {
        // Janvier 2027, en UTC.
        var composants = DateComponents()
        composants.year = 2027
        composants.month = 1
        composants.day = jour
        composants.hour = heure
        composants.minute = minute
        composants.timeZone = TimeZone(identifier: "UTC")
        return utc.date(from: composants)!
    }

    static func executer() {
        let store = SaintexStore.shared
        var echecs = 0
        var total = 0

        func verifier<T: Equatable>(_ nom: String, _ obtenu: T, _ attendu: T) {
            total += 1
            if obtenu != attendu {
                echecs += 1
                store.journal("  ÉCHEC séjours « \(nom) » : attendu \(attendu), obtenu \(obtenu)")
            }
        }

        // --- Entrées et oscillations --------------------------------------------------

        // Première entrée : une alerte, puis plus rien.
        verifier("entrée puis silence",
                 rejouer([(0, [1]), (1, [1]), (5, [1])]),
                 [[1], [], []])

        // Oscillation autour d'un bord : dehors 10 min puis de nouveau dedans = même séjour.
        verifier("oscillation de bord",
                 rejouer([(0, [1]), (0.17, []), (0.33, [1]), (0.5, []), (0.67, [1])]),
                 [[1], [], [], [], []])

        // Dehors plus de 12 h : le retour est une nouvelle entrée (première position dehors à 1 h,
        // retour à 14 h, soit 13 h plus tard).
        verifier("retour après plus de 12 h",
                 rejouer([(0, [1]), (1, []), (14, [1])]),
                 [[1], [], [1]])

        // Dehors moins de 12 h : même séjour (1 h → 12 h = 11 h dehors).
        verifier("retour avant 12 h",
                 rejouer([(0, [1]), (1, []), (12, [1])]),
                 [[1], [], []])

        // Séjour clos par une observation dehors tardive, puis retour : nouvelle entrée.
        verifier("séjour clos puis nouvelle entrée",
                 rejouer([(0, [1]), (1, []), (14, []), (15, [1])]),
                 [[1], [], [], [1]])

        // Plusieurs endémies : suivies indépendamment.
        verifier("endémies indépendantes",
                 rejouer([(0, [1]), (1, [1, 2]), (2, [2])]),
                 [[1], [2], []])

        // Entrée simultanée dans deux endémies : dans l'ordre des identifiants.
        verifier("entrées simultanées",
                 rejouer([(0, [5, 3])]),
                 [[3, 5]])

        // --- Dates de rappel ----------------------------------------------------------

        func rappels(_ delai: DelaiRappel, entree: Date, maintenant: Date? = nil, nombre: Int = 3) -> [Date] {
            Sejours.datesDeRappel(
                entreeLe: entree, maintenant: maintenant ?? entree, delai: delai, calendrier: utc, nombre: nombre
            )
        }

        // Quotidien : chaque jour suivant à 9 h, quelle que soit l'heure d'entrée.
        verifier("rappels quotidiens",
                 rappels(.quotidien, entree: date(15, 8)),
                 [date(16, 9), date(17, 9), date(18, 9)])

        // Entrée tard le soir : le premier rappel est le lendemain matin, pas en pleine nuit.
        verifier("entrée tardive, rappel le lendemain matin",
                 rappels(.quotidien, entree: date(15, 22), nombre: 1),
                 [date(16, 9)])

        // Tous les 2 jours et hebdomadaire.
        verifier("tous les deux jours",
                 rappels(.tousLesDeuxJours, entree: date(15, 8), nombre: 2),
                 [date(17, 9), date(19, 9)])
        verifier("hebdomadaire",
                 rappels(.hebdomadaire, entree: date(15, 8), nombre: 2),
                 [date(22, 9), date(29, 9)])

        // « Une fois » : aucun rappel.
        verifier("une fois, aucun rappel", rappels(.uneFois, entree: date(15, 8)), [])

        // Séjour déjà long : seuls les rappels à venir sont programmés.
        verifier("rappels déjà échus ignorés",
                 rappels(.quotidien, entree: date(15, 8), maintenant: date(18, 10), nombre: 2),
                 [date(19, 9), date(20, 9)])

        // Un rappel pile à l'heure n'est plus « à venir ».
        verifier("rappel à l'instant même ignoré",
                 rappels(.quotidien, entree: date(15, 8), maintenant: date(16, 9), nombre: 1),
                 [date(17, 9)])

        // Le nombre demandé est respecté (et 0 donne une liste vide).
        verifier("nombre de rappels", rappels(.quotidien, entree: date(15, 8), nombre: 5).count, 5)
        verifier("zéro rappel", rappels(.quotidien, entree: date(15, 8), nombre: 0), [])

        store.journal("Auto-test séjours : \(total - echecs)/\(total) OK" + (echecs == 0 ? " ✅" : " ❌"))
    }
}
#endif
