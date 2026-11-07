import Foundation

// Détection locale de l'entrée en zone à risque (cf. spec §5 « Détection
// locale » et §9). IMPLÉMENTATION SWIFT de la référence Python
// `risks.cache.endemies_actives_dans_cache` : elle doit donner EXACTEMENT les
// mêmes résultats sur tests_partages/detection_cache.json.
//
// Règles (le détail fait foi dans `regles` du fichier JSON) :
// - une endémie est active si : instant dans [valide_du, valide_au] (bornes
//   incluses, nulle = sans limite) ET mois (UTC) dans la saison de sa
//   modulation (saison.debut > saison.fin = à cheval sur le nouvel an) ET
//   position dans sa géométrie ;
// - « dans la géométrie » = à l'intérieur OU sur le bord (covers) ; un point
//   dans un trou est dehors, un point sur le bord d'un trou est sur le bord
//   du polygone, donc dedans ;
// - test planaire sur [lon, lat], sans recomposition de l'antiméridien ;
// - résultat : identifiants d'endémies triés par ordre croissant.

enum Detection {
    /// Raccourci pour les tests : construit un détecteur à usage unique.
    static func endemiesActives(cache: CacheMondial, lon: Double, lat: Double, instant: Date) -> [Int] {
        return Detecteur(cache: cache).endemiesActives(lon: lon, lat: lat, instant: instant)
    }
}

/// Dates ISO 8601 du cache (avec ou sans fraction de seconde, avec décalage).
enum DatesISO {
    private static let sansFraction: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime]
        return f
    }()

    private static let avecFraction: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return f
    }()

    static func date(_ texte: String) -> Date? {
        return sansFraction.date(from: texte) ?? avecFraction.date(from: texte)
    }

    static func texte(_ date: Date) -> String {
        return sansFraction.string(from: date)
    }
}

final class Detecteur {
    let version: String

    private struct Point {
        let x: Double
        let y: Double
    }

    /// Géométrie préparée : polygones (anneaux, le premier extérieur) et
    /// rectangle englobant calculé une fois, pour écarter vite les zones
    /// lointaines (le cache réel est mondial : ~500 endémies, ~260 géométries).
    private struct Geometrie {
        let polygones: [[[Point]]]
        let minX: Double
        let minY: Double
        let maxX: Double
        let maxY: Double

        init?(_ source: CacheGeometrie) {
            var polygones: [[[Point]]] = []
            var minX = Double.infinity, minY = Double.infinity
            var maxX = -Double.infinity, maxY = -Double.infinity
            for polygone in source.coordinates {
                var anneaux: [[Point]] = []
                for anneau in polygone {
                    let points = anneau.compactMap { c -> Point? in
                        c.count >= 2 ? Point(x: c[0], y: c[1]) : nil
                    }
                    guard points.count >= 3 else { continue }
                    anneaux.append(points)
                }
                // Seul l'anneau extérieur (le premier) définit l'emprise.
                guard let exterieur = anneaux.first else { continue }
                for p in exterieur {
                    minX = min(minX, p.x); maxX = max(maxX, p.x)
                    minY = min(minY, p.y); maxY = max(maxY, p.y)
                }
                polygones.append(anneaux)
            }
            if polygones.isEmpty { return nil }
            self.polygones = polygones
            self.minX = minX; self.minY = minY; self.maxX = maxX; self.maxY = maxY
        }

        func couvre(x: Double, y: Double) -> Bool {
            if x < minX || x > maxX || y < minY || y > maxY { return false }
            for polygone in polygones where Geometrie.polygoneCouvre(polygone, x: x, y: y) {
                return true
            }
            return false
        }

        private static func polygoneCouvre(_ anneaux: [[Point]], x: Double, y: Double) -> Bool {
            // Sur le bord (extérieur ou d'un trou) : couvert, comme `covers`.
            for anneau in anneaux where surLeBord(anneau, x: x, y: y) {
                return true
            }
            guard let exterieur = anneaux.first, contient(exterieur, x: x, y: y) else { return false }
            for trou in anneaux.dropFirst() where contient(trou, x: x, y: y) {
                return false
            }
            return true
        }

        /// Nombre de croisements (even-odd) : le point est-il à l'intérieur
        /// strict de l'anneau ? (le bord est traité séparément.)
        private static func contient(_ anneau: [Point], x: Double, y: Double) -> Bool {
            var dedans = false
            var j = anneau.count - 1
            for i in 0..<anneau.count {
                let pi = anneau[i], pj = anneau[j]
                if (pi.y > y) != (pj.y > y),
                   x < (pj.x - pi.x) * (y - pi.y) / (pj.y - pi.y) + pi.x {
                    dedans.toggle()
                }
                j = i
            }
            return dedans
        }

        /// Le point est-il sur un segment de l'anneau ? Tolérance minuscule sur
        /// le produit vectoriel : les cas « bord » du jeu partagé sont sensibles
        /// à l'arithmétique flottante (Shapely utilise des prédicats exacts).
        private static func surLeBord(_ anneau: [Point], x: Double, y: Double) -> Bool {
            let epsilon = 1e-12
            var j = anneau.count - 1
            for i in 0..<anneau.count {
                let a = anneau[j], b = anneau[i]
                j = i
                let produit = (b.x - a.x) * (y - a.y) - (b.y - a.y) * (x - a.x)
                if abs(produit) > epsilon { continue }
                if x >= min(a.x, b.x) - epsilon, x <= max(a.x, b.x) + epsilon,
                   y >= min(a.y, b.y) - epsilon, y <= max(a.y, b.y) + epsilon {
                    return true
                }
            }
            return false
        }
    }

    private struct Entree {
        let id: Int
        let du: Date?
        let au: Date?
        let saison: CacheSaison?
        let geometrie: Geometrie?
    }

    private let entrees: [Entree]

    private static let calendrierUTC: Calendar = {
        var calendrier = Calendar(identifier: .gregorian)
        calendrier.timeZone = TimeZone(identifier: "UTC")!
        return calendrier
    }()

    init(cache: CacheMondial) {
        self.version = cache.version

        var geometries: [String: Geometrie] = [:]
        for (cle, source) in cache.geometries {
            if let geometrie = Geometrie(source) {
                geometries[cle] = geometrie
            }
        }

        // Une date illisible est traitée comme « sans limite » : mieux vaut une
        // alerte de trop qu'une alerte manquée (ne doit pas arriver : le
        // serveur produit des dates ISO 8601).
        self.entrees = cache.endemies.map { e in
            let saison = e.modulation.flatMap { cache.modulations[$0]?.saison }
            return Entree(
                id: e.id,
                du: e.valideDu.flatMap(DatesISO.date),
                au: e.valideAu.flatMap(DatesISO.date),
                saison: saison,
                geometrie: geometries[e.geometrie]
            )
        }
    }

    /// Identifiants des endémies actives à (`lon`, `lat`) à l'`instant` donné,
    /// triés par ordre croissant.
    func endemiesActives(lon: Double, lat: Double, instant: Date) -> [Int] {
        let mois = Detecteur.calendrierUTC.component(.month, from: instant)
        var actives: [Int] = []
        for entree in entrees {
            if let du = entree.du, instant < du { continue }
            if let au = entree.au, instant > au { continue }
            if let saison = entree.saison, !Detecteur.enSaison(saison, mois: mois) { continue }
            guard let geometrie = entree.geometrie, geometrie.couvre(x: lon, y: lat) else { continue }
            actives.append(entree.id)
        }
        return actives.sorted()
    }

    private static func enSaison(_ saison: CacheSaison, mois: Int) -> Bool {
        if saison.debut <= saison.fin {
            return mois >= saison.debut && mois <= saison.fin
        }
        return mois >= saison.debut || mois <= saison.fin
    }
}
