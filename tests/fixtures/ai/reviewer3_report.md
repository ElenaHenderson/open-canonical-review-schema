# Review Report

Multi-source forecasting of bay temperatures in the Brannock cold-storage depot

---

### Overview

- **Multi-Source Bay Temperature Forecasting Architecture** — The authors build one deep-learning model that combines unsynchronized readings from a ceiling thermal array inside a freezer hall with snapshots of the truck yard and dock doors to forecast bay temperatures at several dispatch horizons up to 60 minutes.
- **Improved Long-Lead Forecast Accuracy** — The study demonstrates that at a 30-minute lead, the model lowers temperature error by 14% and missed warm bays by 22% relative to the depot's deployed door-event regression.
- **Complementary Sensor Roles** — Ablation experiments show that the in-hall array carries most of the short-lead skill, while the yard feed supplies the long-lead warning of warm air arriving with trucks that have not yet docked.

### AI Text Detection

29% AI-generated and 0% AI-assisted text detected. See the full Pangram report in the app.

### Fatal Flaws

No fatal methodological flaws were identified.

### Reference Check

Checked **52** references: 50 verified, 2 not found.

| # | Citation | Status |
| --- | --- | --- |
| 9 | R. Vantongeren, K. Osei and L. Brask, “BCSD refrigeration plant specifications,” Tech. Rep. HFC-17, Harrowgate Freight Cooperative (2021). | **Not Found** |
| 21 | T. Marchetti, Keeping the Cold In: Event-Aware Door Scheduling for Refrigerated Depots. PhD thesis, Kestrel Ford Polytechnic, School of Mechanical Engineering (2026). | **Not Found** |

### Reviewer Comments

1. **Symbolcollision for κ between time constant and threshold**

In Section 2.6, Eq. (6) (page 20), $\kappa$ is defined as the thermal time constant of the hall ($\hat{\theta} = \theta_{\text{sup}} + (\theta_0 - \theta_{\text{sup}}) e^{-H/\kappa} + \alpha g \Delta\theta$). On the next page, in Section 2.7, Eq. (9) (page 21), the same symbol $\kappa$ is used without definition for the warm-bay threshold ($-15^\circ\text{C}$) in the missed-warm loss: $\mathcal{L}_{\text{MW}} = \frac{1}{|W|} \sum_{i \in W} \text{ReLU}(\kappa - \hat{\theta}_i), \quad W = \{i : \theta_i \ge \kappa, \text{valid}, d_i \ge 6\,\text{m}\}$.

2. **Contradictory Gaussian smoothing widths and sweeps for CTA maps** — Page 8

> sensor drift while keeping the aisle structure. We Gaussian-smooth θ over neighbouring bays with σ = 2 . 5 bay pitches ( ∼ 3 . 0 m at a 1 . 2 m pitch ) before labelling, and we smooth the last-sweep θ the same way, so the residual does not come from smoothing only the future observed CTA temperature. The same reasoning motivates small Gaussian kernels on CTA floor-plan rasters

Section 2.1 (page 8) and Section 2.3 (page 10) state that the bay temperature $\theta$ is smoothed over neighboring bays with $\sigma = 2.5$ bay pitches, and that "Only the final sweep and the target are smoothed, as described in Sect. 2.1." A later paragraph of Section 2.1 (page 9) gives a different kernel width, a different grid and a different set of sweeps: "In addition, we applied a Gaussian smoothing kernel to the CTA temperature maps... Each sweep is smoothed with $\sigma = 6$ grid cells, a standard kernel similar to that in.21 ... Fig. 1(a) shows six sequences of CTA bay maps to show how the smoothing affects the maps and how warm plumes evolve with time." The caption of Fig. 1(a) (page 11), meanwhile, reads "Gaussian-smoothed ($\sigma = 2.5$) CTA bay temperature over the hour ending at $t_{\text{end}}$".

3. **Missing panel labels (b), (d), (f) in Figure 3** — Page 26

> Fig 3

Figure 3 (page 26) has three rows of plots, each with a left panel (Median $\Delta\text{MARE}$) and a right panel (Win fraction). Only the left panels carry labels, `(a) Persistence`, `(c) Door-event reg.` and `(e) StackTCN`, so `(b)`, `(d)` and `(f)` never appear. The caption and the text on page 27 nevertheless refer to `Fig. 3(a), (c), and (e)` as if they covered both panels of each row.

4. **Inconsistent dry-bulb normalization formula between text and Table 1** — Page 12

> Each channel then receives its own normalization: occ is clipped to [0 , 1] , humidity is scaled by [0 , 100] / 100 , door open or held is a 0 , 1 mask, dry bulb is normalized as ( ◦ C − 18) / 9 , dew point as ( ◦ C + 2) / 6 , ∆ rat is clipped to (∆ K/ 10 , 2) , and ∆ occ is clipped to

In Section 2.3 (page 12), the prose normalizes the outdoor dry-bulb temperature by subtracting 18 °C: "dry bulb is normalized as $(^\circ\text{C} - 18)/9$". Table 1 (page 13) gives the normalization for channel `tdb` (Outdoor dry bulb) as "$(T_{\text{db}} - 15)/9$".

5. **MARE metric heading defines MSE loss instead of MAE** — Page 22

> Mean absolute recovery-energy error (MARE). The recovery energy at a fixed coil duty is E rec ∝ θ − θ sup (Eq. 1), so a squared error on bay temperature is a squared error on recovery energy. The train loss is the occupancy-weighted mean squared error of ˆ θ against the observed CTA temperature 22 at t end + H , the square of the MARE residual in Sect. 2.8:

In Section 2.8 (page 22–23), the first metric paragraph is headed "Mean absolute recovery-energy error (MARE)." The paragraph and its equation (Eq. 11) never define MARE, however: they restate the mean squared error training loss $\mathcal{L}$ (reported as "load MSE" in Tables 3 and 4) and describe $\mathcal{L}$, circularly, as "the square of the MARE residual in Sect. 2.8". Equation 11 gives the squared error $\mathcal{L} = \frac{\sum_i w_i (\hat{\theta}_i - \theta_i)^2}{\sum_i w_i}$, and the MARE itself ($\frac{\sum_i w_i |\hat{\theta}_i - \theta_i|}{\sum_i w_i}$) is never written down.

6. **Bay encoder feature count: 6 features versus 7 channels** — Page 16

> take individual sweeps and use the bay encoder as a spatial embedder. Each sweep produces 6 features per node (bay) in the graph layers. The first feature is θ , then the first and sec- ond differences ∆ θ and ∆ 2 θ (zero where either sweep is missing, so a gap is not a trend), and ( x, y, ℓ ) with x, y the bay position and ℓ the rack level. A sensor-valid flag is concatenated as a seventh channel. A two-block GraphAttn network of hidden width

In Section 2.6 (page 16), under "Bay encoder", the text states: "Each sweep produces 6 features per node (bay) in the graph layers. The first feature is $\theta$, then the first and second differences $\Delta \theta$ and $\Delta^2 \theta$ (zero where either sweep is missing, so a gap is not a trend), and $(x, y, \ell)$ with $x, y$ the bay position and $\ell$ the rack level. A sensor-valid flag is concatenated as a seventh channel." Giving 6 as the number of features per node and then adding a seventh channel leaves the input size of the first GraphAttn layer unclear (6 or 7).
