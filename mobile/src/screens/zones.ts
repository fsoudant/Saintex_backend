import { Preferences as CapPreferences } from '@capacitor/preferences';
import { showScreen } from '../router';
import type { ConseilCache, RisqueAffiche, ZonesAffichees } from '../types';

// Accueil : les risques présents à la position ACTUELLE du téléphone, avec la conduite à tenir.
//
// Tout vient du module natif Swift, qui détecte la zone à partir du cache du serveur et écrit
// une synthèse dans UserDefaults (SaintexService.publierZonesActuelles) ; cet écran se contente
// de la lire et de l'afficher. Aucune coordonnée n'y figure et rien n'est demandé au serveur :
// l'écran fonctionne hors connexion.
//
// Fiches conseil : une recommandation peut contenir des liens `conseil:<code>` (cf.
// risks/richtext.py) vers une fiche partagée entre plusieurs risques (ex. protection contre les
// moustiques). Un clic ouvre la fiche, lue elle aussi dans la synthèse (donc dans le cache), sur
// un écran avec un bouton « Retour ». Un lien vers une fiche absente s'affiche en simple texte.
const ZONES_KEY = 'saintex_zones_actuelles';
const PREFIXE_CONSEIL = 'conseil:';

// L'écran relit la synthèse à intervalle régulier tant qu'il est visible : l'ouverture de
// l'appli déclenche une nouvelle position côté natif, dont le résultat arrive quelques
// secondes plus tard.
const INTERVALLE_RAFRAICHISSEMENT_MS = 5000;

const COULEUR_VALIDE = /^#[0-9a-fA-F]{3,8}$/;
const BALISES_INTERDITES = 'script,style,iframe,object,embed,link,meta,form,input,button,svg,math';

let derniereSignature: string | null = null;
let conseilsCourants: Record<string, ConseilCache> = {};
let defilementAvantConseil = 0;

function echapper(texte: string): string {
  return texte.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
}

function enFrancais(): boolean {
  return (navigator.language || 'fr').toLowerCase().startsWith('fr');
}

function formaterDate(iso: string, fr: boolean, avecHeure: boolean): string | null {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return null;
  return new Intl.DateTimeFormat(
    fr ? 'fr-FR' : 'en-GB',
    avecHeure ? { dateStyle: 'medium', timeStyle: 'short' } : { dateStyle: 'medium' },
  ).format(date);
}

// Les textes du cache sont du HTML déjà assaini par le serveur ; on le nettoie encore ici
// (défense en profondeur) avant de l'insérer : balises actives, attributs d'événements,
// styles en ligne et liens « javascript: » retirés. Les liens `conseil:<code>` vers une fiche
// connue (`conseils`) deviennent cliquables ; vers une fiche absente, ils sont réduits à leur texte.
function assainirHtml(html: string, conseils: Record<string, ConseilCache>): string {
  const doc = new DOMParser().parseFromString(html, 'text/html');
  doc.querySelectorAll(BALISES_INTERDITES).forEach((el) => el.remove());
  doc.body.querySelectorAll('*').forEach((el) => {
    for (const attr of Array.from(el.attributes)) {
      const nom = attr.name.toLowerCase();
      const valeur = attr.value.trim().toLowerCase();
      const lienDangereux =
        (nom === 'href' || nom === 'src') && /^(javascript|data|vbscript):/.test(valeur);
      if (nom.startsWith('on') || nom === 'style' || lienDangereux) el.removeAttribute(attr.name);
    }
  });
  doc.body.querySelectorAll('a').forEach((lien) => {
    const href = lien.getAttribute('href') ?? '';
    if (!href.startsWith(PREFIXE_CONSEIL)) return;
    const code = href.slice(PREFIXE_CONSEIL.length);
    if (Object.prototype.hasOwnProperty.call(conseils, code)) {
      lien.setAttribute('href', '#');
      lien.setAttribute('data-conseil', code);
      lien.classList.add('conseil-link');
    } else {
      lien.replaceWith(...Array.from(lien.childNodes));
    }
  });
  return doc.body.innerHTML;
}

function estVide(html: string): boolean {
  const doc = new DOMParser().parseFromString(html, 'text/html');
  return (doc.body.textContent ?? '').trim() === '';
}

function majusculeInitiale(texte: string): string {
  return texte ? texte.charAt(0).toUpperCase() + texte.slice(1) : texte;
}

function rendreRisque(
  entree: RisqueAffiche,
  fr: boolean,
  conseils: Record<string, ConseilCache>,
): string {
  const risque = entree.risque;
  const libelle = fr ? risque.libelle_fr : risque.libelle_en;
  const alerte = fr ? risque.alerte_fr : risque.alerte_en;
  const modulation = (fr ? entree.modulation_fr : entree.modulation_en) ?? '';
  const description = fr ? risque.description_fr : risque.description_en;
  const recommandation = fr ? risque.recommandation_fr : risque.recommandation_en;

  const couleur = risque.couleur && COULEUR_VALIDE.test(risque.couleur) ? risque.couleur : null;
  const style = couleur ? ` style="border-left-color: ${couleur}"` : '';

  const zones = entree.zones.length
    ? `<p class="risk-zones">${fr ? 'Zone' : 'Area'} : ${echapper(entree.zones.join(', '))}</p>`
    : '';
  const phrase = majusculeInitiale([alerte, modulation].filter(Boolean).join(' ').trim());

  let corps = '';
  if (!estVide(recommandation)) {
    corps += `<h4>${fr ? 'Conduite à tenir' : 'What to do'}</h4><div class="risk-html">${assainirHtml(recommandation, conseils)}</div>`;
  }
  if (!estVide(description)) {
    const contenu = `<div class="risk-html">${assainirHtml(description, conseils)}</div>`;
    corps += estVide(recommandation)
      ? contenu
      : `<details><summary>${fr ? 'En savoir plus' : 'More information'}</summary>${contenu}</details>`;
  }

  return `
    <article class="risk-card"${style}>
      <h3>${echapper(libelle)}</h3>
      ${zones}
      ${phrase ? `<p class="risk-alert">${echapper(phrase)}</p>` : ''}
      ${corps}
    </article>
  `;
}

async function lireSynthese(): Promise<{ brut: string | null; zones: ZonesAffichees | null }> {
  const { value } = await CapPreferences.get({ key: ZONES_KEY });
  if (!value) return { brut: null, zones: null };
  try {
    return { brut: value, zones: JSON.parse(value) as ZonesAffichees };
  } catch (error) {
    console.error('Synthèse des zones illisible :', error);
    return { brut: value, zones: null };
  }
}

function carte(texte: string): string {
  return `<div class="card"><p class="status-detail">${echapper(texte)}</p></div>`;
}

export async function renderZones(): Promise<void> {
  const conteneur = document.getElementById('zones-container');
  const maj = document.getElementById('zones-updated');
  if (!conteneur) return;

  const { brut, zones } = await lireSynthese();
  const signature = brut ?? '';
  if (signature === derniereSignature) return; // rien de nouveau : pas de réaffichage
  derniereSignature = signature;

  const fr = enFrancais();
  conseilsCourants = zones?.conseils ?? {};

  if (!zones) {
    conteneur.innerHTML = carte(
      fr
        ? "Saintex n'a pas encore analysé votre position. Cela se fait automatiquement, en arrière-plan."
        : 'Saintex has not analysed your position yet. This happens automatically in the background.',
    );
    if (maj) maj.textContent = '';
    return;
  }

  if (zones.contrat_actif === false) {
    // Avant le début ou après la fin du contrat le téléphone est muet : une liste vide
    // ne veut pas dire « pas de risque ici ».
    conteneur.innerHTML = carte(
      fr
        ? "Saintex est en veille : votre contrat n'a pas encore commencé ou est terminé. Les dates figurent dans l'onglet Préférences."
        : 'Saintex is on standby: your contract has not started yet or has ended. The dates are in the Preferences tab.',
    );
  } else if (zones.risques.length) {
    conteneur.innerHTML = zones.risques.map((r) => rendreRisque(r, fr, conseilsCourants)).join('');
  } else {
    conteneur.innerHTML = carte(
      fr
        ? 'Aucune zone à risque infectieux connue à votre position actuelle.'
        : 'No known infectious-risk area at your current position.',
    );
  }

  if (maj) {
    const date = formaterDate(zones.mis_a_jour_le, fr, true);
    maj.textContent = date
      ? `${fr ? 'Dernière analyse de votre position' : 'Position last analysed'} : ${date}`
      : '';
  }
}

// --- Fiche conseil --------------------------------------------------------------------------

function ouvrirConseil(code: string): void {
  const conseil = conseilsCourants[code];
  const titre = document.getElementById('conseil-titre');
  const contenu = document.getElementById('conseil-contenu');
  const maj = document.getElementById('conseil-maj');
  if (!conseil || !titre || !contenu) return;

  const fr = enFrancais();
  titre.textContent = fr ? conseil.titre_fr : conseil.titre_en;
  // Une fiche ne renvoie pas vers une autre fiche : aucun lien `conseil:` n'y est activé.
  contenu.innerHTML = assainirHtml(fr ? conseil.contenu_fr : conseil.contenu_en, {});
  if (maj) {
    const date = conseil.modifie_le ? formaterDate(conseil.modifie_le, fr, false) : null;
    maj.textContent = date ? `${fr ? 'Fiche mise à jour le' : 'Updated on'} ${date}` : '';
  }

  defilementAvantConseil = window.scrollY;
  showScreen('conseil');
  window.scrollTo(0, 0);
}

function fermerConseil(): void {
  showScreen('home');
  window.scrollTo(0, defilementAvantConseil);
}

function ecranAccueilVisible(): boolean {
  const ecran = document.getElementById('screen-home');
  return !!ecran && !ecran.classList.contains('hidden');
}

export function initZonesScreen(): void {
  const rafraichir = () => {
    if (document.visibilityState !== 'visible' || !ecranAccueilVisible()) return;
    renderZones().catch((error) => console.error("Impossible d'afficher les zones :", error));
  };
  document.addEventListener('visibilitychange', rafraichir);
  window.setInterval(rafraichir, INTERVALLE_RAFRAICHISSEMENT_MS);
  for (const id of ['nav-home', 'nav-home-2']) {
    document.getElementById(id)?.addEventListener('click', () => {
      renderZones().catch((error) => console.error("Impossible d'afficher les zones :", error));
    });
  }

  // Un seul écouteur pour tous les liens vers une fiche conseil (le contenu est recréé à chaque
  // mise à jour de la synthèse).
  document.getElementById('zones-container')?.addEventListener('click', (event) => {
    const lien = (event.target as Element | null)?.closest('a[data-conseil]');
    const code = lien?.getAttribute('data-conseil');
    if (!lien || !code) return;
    event.preventDefault();
    ouvrirConseil(code);
  });
  document.getElementById('btn-conseil-retour')?.addEventListener('click', fermerConseil);
}
