# ML

Everything needed to produce a valuation model. The full explanation, including recorded results, is in [docs/ML_PIPELINE.md](../docs/ML_PIPELINE.md).

```powershell
python ml/scripts/generate_dataset.py   # recreate the synthetic dataset (seed 42)
python ml/scripts/train.py              # writes a candidate to ml/artifacts/<version>/
```

| Path | Contents |
|---|---|
| `data/synthetic_transactions.csv` | Fictional sales. Not real market data |
| `scripts/` | Dataset generator and training command |
| `preprocessing/` | Validation, cleaning, splitting, encoding |
| `models/` | Baselines and the training loop |
| `evaluation/` | Metrics and the conformal interval |
| `artifacts/` | Trained models. Git-ignored and never edited after creation |

The network and feature definitions live in `backend/app/ml/`, because the API needs them at runtime and training must use exactly the same ones.

A trained model does nothing until an administrator promotes it.
