// Dates « jour » (AAAA-MM-JJ) du contrat. Le serveur raisonne en jours
// calendaires (clients.models.valider_date_debut_contrat, timezone.localdate()) :
// on compare donc des chaînes ISO de jour, sans passer par des instants UTC,
// qui décaleraient d'un jour autour de minuit.

function deuxChiffres(n: number): string {
  return String(n).padStart(2, '0');
}

// Date du jour, à l'heure locale du téléphone.
export function aujourdhuiISO(): string {
  const maintenant = new Date();
  return `${maintenant.getFullYear()}-${deuxChiffres(maintenant.getMonth() + 1)}-${deuxChiffres(maintenant.getDate())}`;
}

// « 14 mars 2027 » ; chaîne vide si la date est absente.
export function formaterDate(dateISO: string | null): string {
  if (!dateISO) return '';
  const [annee, mois, jour] = dateISO.split('-').map(Number);
  return new Date(annee, mois - 1, jour).toLocaleDateString('fr-FR', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  });
}

// Les chaînes AAAA-MM-JJ se comparent correctement dans l'ordre alphabétique.
export function departAtteint(dateDepartISO: string | null): boolean {
  return dateDepartISO !== null && aujourdhuiISO() >= dateDepartISO;
}
