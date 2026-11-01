# Évolution d'octobre 2026 — recommandation unique par risque, `Modulation`
# (cf. saintex-spec-technique.md §7 et §8). Étape 2/3 : conversion des données.
#
# Conversion mécanique, SANS perte de zones ni d'endémies :
# 1. chaque endémie reçoit le `risque` de son ancienne conduite ;
# 2. chaque risque reçoit comme recommandation unique celle de sa première
#    ancienne conduite renseignée (ordre alphabétique du code). Provisoire :
#    les textes définitifs seront saisis par l'équipe médicale (rédigés sur
#    Word). Si le risque n'a pas encore de couleur de légende, il reprend
#    celle de sa première conduite qui en a une ;
# 3. une modulation sans phrase ET sans période n'a pas de raison d'être : les
#    endémies qui la référençaient n'ont plus de modulation (champ facultatif),
#    et la ligne est supprimée. Les modulations qui ont une phrase ou une
#    période sont conservées telles quelles.
#
# La migration s'arrête (et tout est annulé, la transaction étant atomique) si
# une endémie ne peut pas être rattachée à un risque.
#
# Pas de retour arrière automatique : sauvegarder la base (pg_dump) avant de
# l'appliquer.

from django.db import migrations
from django.db.models import OuterRef, Subquery


def convertir(apps, schema_editor):
    Risque = apps.get_model('risks', 'Risque')
    Modulation = apps.get_model('risks', 'Modulation')
    Endemie = apps.get_model('risks', 'Endemie')

    # 1. Risque des endémies, repris de l'ancienne conduite.
    Endemie.objects.filter(risque__isnull=True).update(
        risque_id=Subquery(
            Modulation.objects.filter(pk=OuterRef('modulation_id')).values('risque_id')[:1]
        )
    )
    sans_risque = Endemie.objects.filter(risque__isnull=True).count()
    if sans_risque:
        raise RuntimeError(
            f"{sans_risque} endémie(s) sans risque après conversion : migration annulée."
        )

    # 2. Recommandation unique par risque (+ couleur de légende si absente).
    for risque in Risque.objects.all():
        conduites = list(Modulation.objects.filter(risque_id=risque.pk).order_by('code'))
        modifications = {}
        if not (risque.recommandation_fr or '').strip() and not (risque.recommandation_en or '').strip():
            source = next((c for c in conduites if (c.recommandation_fr or '').strip()), None)
            if source is None:
                source = next((c for c in conduites if (c.recommandation_en or '').strip()), None)
            if source is not None:
                modifications['recommandation_fr'] = source.recommandation_fr
                modifications['recommandation_en'] = source.recommandation_en
        if not risque.couleur_legende:
            couleur = next((c.couleur for c in conduites if c.couleur), None)
            if couleur:
                modifications['couleur_legende'] = couleur
        if modifications:
            # update() plutôt que save() : le modèle historique n'a pas le
            # save() applicatif (les textes sont déjà du HTML assaini).
            Risque.objects.filter(pk=risque.pk).update(**modifications)

    # 3. Modulations sans phrase ni période : détachées puis supprimées.
    vides = [
        m.pk for m in Modulation.objects.all()
        if not (m.modulation_fr or '').strip()
        and not (m.modulation_en or '').strip()
        and m.saison_mois_debut is None
    ]
    if vides:
        Endemie.objects.filter(modulation_id__in=vides).update(modulation=None)
        Modulation.objects.filter(pk__in=vides).delete()

    if Endemie.objects.exists():
        print(
            f"\n  [0011] {Endemie.objects.count()} endémies rattachées à un risque, "
            f"{Modulation.objects.count()} modulations conservées, {len(vides)} supprimées "
            f"(sans phrase ni période), "
            f"{Risque.objects.exclude(recommandation_fr='').count()}/{Risque.objects.count()} "
            f"risques avec une recommandation."
        )


class Migration(migrations.Migration):

    dependencies = [
        ('risks', '0010_modulation_schema'),
    ]

    operations = [
        migrations.RunPython(convertir, migrations.RunPython.noop),
    ]
