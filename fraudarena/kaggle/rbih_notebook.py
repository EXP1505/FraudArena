# Kaggle notebook version: paste each "# %%" block into its own cell (or upload this file and run it).
# Settings: Accelerator = GPU (T4 / P100), Internet = On (only needed for `pip install duckdb`).
# Add TWO inputs: the competition dataset (rbih-nfpc-phase-2) and your uploaded dataset that holds the
# kaggle/ code folder (the .py files next to this one).

# %% 0. setup
import glob, os, subprocess, sys
subprocess.run([sys.executable, "-m", "pip", "install", "-q", "duckdb"], check=False)
CODE_DIR = next(d for d in glob.glob("/kaggle/input/*") if os.path.exists(os.path.join(d, "rbih_run.py")))
sys.path.insert(0, CODE_DIR)
from rbih_config import CFG
print("code:", CODE_DIR); print(sorted(glob.glob("/kaggle/input/*")))

# %% 1. point at the data (auto-detects files named *transaction*/*txn* and *label*; set paths here if it fails)
# CFG.txn_glob = "/kaggle/input/rbih-nfpc-phase-2/transactions_*.parquet"
# CFG.labels_path = "/kaggle/input/rbih-nfpc-phase-2/train_labels.csv"
# CFG.amount_to_paise = 100        # 100 if amounts are in rupees, 1 if already in paise (stage 1 shows the range)

# %% 2. STAGE 1: inspect (about 10 minutes). Download /kaggle/working/artifacts/rbih/schema_report.json and send it back.
from rbih_inspect import inspect
import json
rep = inspect(CFG)
print(json.dumps({k: rep[k] for k in ("mapping", "warnings", "labels", "join", "labelling_rule_check")}, indent=1, default=str))

# %% 3. STAGE 2: build features, train, export (run after we confirm the mapping; ~1-3 hours on the full data)
# Optional: CFG.legit_account_frac = 0.10  # lower it if memory runs out; mules are always all kept
from rbih_run import run_train
print(run_train(CFG))

# %% 4. zip the artifacts for download (aggregates + model only: NO transaction rows)
import shutil
shutil.make_archive("/kaggle/working/rbih_artifacts", "zip", CFG.out_dir)
print("Download /kaggle/working/rbih_artifacts.zip")
