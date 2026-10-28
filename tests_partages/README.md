# Jeu de test partagé de la détection locale

La détection de l'entrée en zone à risque existe en **trois exemplaires** : la
référence Python du serveur (`risks/cache.py`, fonction
`endemies_actives_dans_cache`) et les modules natifs **Swift** (iOS) et
**Kotlin** (Android). Ce dossier contient le jeu de cas qui les garde
identiques (cf. `saintex-spec-technique.md` §5 et §9).

## Contenu

`detection_cache.json` (généré, ne pas modifier à la main) :

| Clé | Rôle |
|---|---|
| `regles` | les règles de détection, en clair — à lire avant d'implémenter |
| `cache` | un petit cache de test, au format exact de `POST /api/cache/` |
| `cas` | des cas `{nom, lon, lat, instant, attendu}` ; `attendu` = identifiants d'endémies actives, ordre croissant |

Certains cas portent `"bord": true` : la position est exactement sur le bord
d'un polygone (comportement « inclus »). Ils dépendent de l'arithmétique
flottante : un module natif doit les réussir, ou documenter l'écart.

## Ce que doit faire chaque module natif

Dans ses tests automatiques : charger `detection_cache.json`, et pour chaque cas,
vérifier que la détection locale (cache + position + instant) retourne
**exactement** `attendu`. Un seul cas en échec = une divergence avec la
référence serveur.

Rappel des règles (le détail fait foi dans `regles`) :

- coordonnées `[longitude, latitude]`, longitude dans [-180, 180] ;
- géométries GeoJSON `MultiPolygon` avec trous ; zone à cheval sur
  l'antiméridien = deux parties collées à ±180°, testées telles quelles ;
- dans la zone = à l'intérieur **ou sur le bord** ; dans un trou = hors zone ;
- validité `valide_du` / `valide_au` : bornes **incluses**, `null` = sans limite ;
- saison : mois 1-12 bornes incluses, `debut > fin` = à cheval sur le nouvel an ;
- **le mois est celui de l'instant converti en UTC** ;
- active = dans la validité **et** dans la saison **et** dans la géométrie.

Squelette de test (idée, à adapter) :

```kotlin
// Kotlin / JUnit
val vecteurs = chargerJson("detection_cache.json")
vecteurs.cas.forEach { cas ->
    val obtenu = Detection.endemiesActives(vecteurs.cache, cas.lon, cas.lat, Instant.parse(cas.instant))
    assertEquals(cas.attendu, obtenu.sorted(), cas.nom)
}
```

```swift
// Swift / XCTest
let vecteurs = try chargerJson("detection_cache.json")
for cas in vecteurs.cas {
    let obtenu = Detection.endemiesActives(cache: vecteurs.cache, lon: cas.lon, lat: cas.lat,
                                           instant: isoFormatter.date(from: cas.instant)!)
    XCTAssertEqual(obtenu.sorted(), cas.attendu, cas.nom)
}
```

Point d'attention pour la **performance** : le cache réel est mondial (environ
500 endémies, 260 géométries). Avant le test point-dans-polygone, filtrer par
rectangle englobant de chaque géométrie (calculé une fois au chargement du
cache) pour ne pas tester toutes les zones à chaque mise à jour de position.

## Régénérer / vérifier

```
python manage.py generer_vecteurs_detection             # (ré)écrit detection_cache.json
python manage.py generer_vecteurs_detection --verifier  # échoue si le fichier n'est pas à jour
```

Un test du serveur (`risks/tests/test_vecteurs_detection.py`) échoue si le
fichier n'est plus à jour par rapport à la référence Python. Si le
comportement de la détection change **volontairement**, on régénère le
fichier **et** on met à jour les modules natifs.
