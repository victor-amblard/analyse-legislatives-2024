# Site du billet

Site Astro bilingue qui rend `writeup.fr.md` à la racine et `writeup.md` sous
`/en/`. Les fichiers Markdown restent les sources uniques du contenu ; la
collection Astro les charge directement depuis la racine du dépôt.

```bash
npm install
npm run dev
npm run build
```

Les figures publiées vivent dans `public/figures/` et sont régénérées depuis la
racine avec :

```bash
python scripts/reproduce.py --figures
```

La grille de sensibilité du noyau est volontairement exclue de cette commande ;
pour la recalculer :

```bash
python scripts/reproduce.py --figures --kernel-sensitivity
```
