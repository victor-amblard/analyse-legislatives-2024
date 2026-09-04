# Analyses complémentaires

Ces scripts documentent le comportement du modèle mais ne constituent pas ses
points d'entrée principaux :

- `alpha_sensitivity.py` étudie la concentration de la Dirichlet ;
- `demobilisation_sensitivity.py` fixe le taux national de démobilisation sur une grille ;
- `conditioned_seat_intervals.py` conditionne rétrospectivement les sièges sur la part nationale de suffrages exprimés observée ;
- `kernel_sensitivity.py` étudie conjointement la corrélation intra-département `rho` et le mélange national/local `lambda` ;
- `local_components_effect.py` mesure ce que la localisation du tilt et de l'ordre
  change réellement ;
- `local_tilt_effect.py` isole la localisation du seul tilt ;
- `ordering_sensitivity.py` mesure ce que coûterait un ordre de préférence TOTAL ;
- `tilt_sensitivity.py` fait varier les bornes du prior de tilt ;
- `first_round_variogram.py` teste la structure spatiale des écarts avec le SEUL
  premier tour — c'est lui qui justifie le noyau départemental sans rien devoir au
  second tour ;
- `residual_variogram.py` refait le même test sur les résidus du second tour, donc
  *a posteriori* ;
- `diagnostics.py` mesure le bruit Monte-Carlo et compare les variantes ;
- `prior_predictive.py` résume les taux de report impliqués par les priors ;
- `pollster_benchmark.py` reconstruit prudemment la comparaison aux instituts.

La commande stable destinée à reproduire le billet reste `scripts/reproduce.py`.
