#if DEBUG
import Foundation

/// Rejoue le jeu de test partagé (tests_partages/detection_cache.json) sur
/// la détection locale Swift et écrit le verdict dans le journal : « Auto-test
/// détection : N/N cas OK ». Un seul écart = une divergence avec la référence
/// Python du serveur (risks.cache.endemies_actives_dans_cache).
///
/// Uniquement en build Debug. Le fichier est embarqué par `npm run sync:dev`
/// (copie dans www/dev/, donc dans public/dev/ de l'app) ; le `sync` normal
/// l'écarte du build de production.
enum DetectionSelfTest {
    private struct Vecteurs: Decodable {
        let cache: CacheMondial
        let cas: [Cas]
    }

    private struct Cas: Decodable {
        let nom: String
        let lon: Double
        let lat: Double
        let instant: String
        let attendu: [Int]
        let bord: Bool?
    }

    static func executer() {
        let store = SaintexStore.shared
        guard let url = Bundle.main.url(
            forResource: "detection_cache", withExtension: "json", subdirectory: "public/dev"
        ) else {
            store.journal("Auto-test détection ignoré : jeu de test absent (lancer « npm run sync:dev » dans mobile/)")
            return
        }

        let vecteurs: Vecteurs
        do {
            vecteurs = try JSONDecoder().decode(Vecteurs.self, from: Data(contentsOf: url))
        } catch {
            store.journal("Auto-test détection : jeu de test illisible : \(error)")
            return
        }

        let detecteur = Detecteur(cache: vecteurs.cache)
        var echecs = 0
        for cas in vecteurs.cas {
            guard let instant = DatesISO.date(cas.instant) else {
                echecs += 1
                store.journal("  ÉCHEC « \(cas.nom) » : instant illisible « \(cas.instant) »")
                continue
            }
            let obtenu = detecteur.endemiesActives(lon: cas.lon, lat: cas.lat, instant: instant)
            if obtenu != cas.attendu.sorted() {
                echecs += 1
                let bord = (cas.bord ?? false) ? " [cas de bord]" : ""
                store.journal("  ÉCHEC « \(cas.nom) »\(bord) : attendu \(cas.attendu.sorted()), obtenu \(obtenu)")
            }
        }
        let reussis = vecteurs.cas.count - echecs
        store.journal("Auto-test détection : \(reussis)/\(vecteurs.cas.count) cas OK" + (echecs == 0 ? " ✅" : " ❌"))
    }
}
#endif
