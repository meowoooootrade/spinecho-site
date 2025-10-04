# 1) token
export ENCORA_API_TOKEN="71|2pBMrBwgNfYmBrohrcBmC3kJtkAJzrvDXRemelxccb3b5056"

# 2) dump only
python3 scripts/encora_to_csv.py \
  --out data/encora.csv \
  --per-page 200 \
  # --page 1
  --ids 28930

# # 3) dump + auto-merge (prefer new values; union tags)
# python3 scripts/encora_to_csv.py \
#   --out data/items.encora.csv \
#   --merge-into data/items.csv \
#   --on id \
#   --prefer new \
#   --union-tags
# #   --per-page 100

# 4) build JSON for the site (same as before)
# python3 script/build_items.py
