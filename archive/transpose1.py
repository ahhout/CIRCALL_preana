from openpyxl import load_workbook

INPUT_XLSX  = "cfDNA_inventaire_2025.xlsx"
OUTPUT_XLSX = "cfDNA_inventaire_2025_updated.xlsx"

def normalize_sample_id(sid):
    """Return a stable string form (strip spaces; handle None / numbers)."""
    if sid is None:
        return None
    return str(sid).strip()

def main():
    # 1) Load two copies:
    # - wb_vals: read evaluated values (so formulas in manips resolve to their displayed values)
    # - wb:      real workbook we will modify and save
    wb_vals = load_workbook(INPUT_XLSX, data_only=True)
    wb      = load_workbook(INPUT_XLSX)

    ws_manips_vals = wb_vals["manips"]     # for reading evaluated sample_id values
    ws_manips      = wb["manips"]          # for writing updates
    ws_ddpcr       = wb["ddPCR_test"]      # read ddPCR rows

    # 2) Build header maps (from the writable workbook — layout is identical)
    manips_headers = {cell.value: idx for idx, cell in enumerate(next(ws_manips.iter_rows(min_row=1, max_row=1)), start=1)}
    ddpcr_headers  = {cell.value: idx for idx, cell in enumerate(next(ws_ddpcr.iter_rows(min_row=1, max_row=1)),  start=1)}

    # Sanity checks for required columns
    required_manips = ["sample_id", "ddPCR_status", "ddPCR_targets", "design_length"]
    missing = [c for c in required_manips if c not in manips_headers]
    if missing:
        raise RuntimeError(f"Missing columns in 'manips': {missing}")

    required_ddpcr = ["sample_id", "use for test?", "MRD_system", "system_length"]
    missing = [c for c in required_ddpcr if c not in ddpcr_headers]
    if missing:
        raise RuntimeError(f"Missing columns in 'ddPCR_test': {missing}")

    col_sid_manips  = manips_headers["sample_id"]
    col_status      = manips_headers["ddPCR_status"]
    col_targets     = manips_headers["ddPCR_targets"]
    col_length      = manips_headers["design_length"]

    col_sid_ddpcr   = ddpcr_headers["sample_id"]
    col_use         = ddpcr_headers["use for test?"]
    col_mrd         = ddpcr_headers["MRD_system"]
    col_len         = ddpcr_headers["system_length"]

    # 3) Build an index: sample_id (normalized) -> row number in manips
    #    Use ws_manips_vals so formulas (RECHERCHEX etc.) are evaluated to actual values.
    sid_to_row = {}
    duplicates = set()
    for r in range(2, ws_manips_vals.max_row + 1):
        sid_val = ws_manips_vals.cell(row=r, column=col_sid_manips).value
        sid_norm = normalize_sample_id(sid_val)
        if not sid_norm:
            continue
        if sid_norm in sid_to_row:
            duplicates.add(sid_norm)  # keep first occurrence; note duplicates
        else:
            sid_to_row[sid_norm] = r

    if duplicates:
        print(f"⚠️  Note: duplicate sample_id(s) in 'manips' (first occurrence will be updated): {sorted(list(duplicates))[:5]}{' ...' if len(duplicates)>5 else ''}")

    # 4) Iterate ddPCR_test and update manips
    updated = 0
    not_found = 0
    skipped = 0

    for row in ws_ddpcr.iter_rows(min_row=2):
        sid_val   = row[col_sid_ddpcr - 1].value
        use_val   = row[col_use        - 1].value
        mrd_sys   = row[col_mrd        - 1].value
        sys_len   = row[col_len        - 1].value

        # only process if "use for test?" says yes (case-insensitive)
        if str(use_val).strip().lower() != "yes":
            skipped += 1
            continue

        sid_norm = normalize_sample_id(sid_val)
        if not sid_norm:
            not_found += 1
            print("⚠️  Warning: blank/None sample_id in ddPCR_test row; skipped")
            continue

        r_manips = sid_to_row.get(sid_norm)
        if not r_manips:
            not_found += 1
            print(f"⚠️  Warning: sample_id '{sid_norm}' not found in 'manips'")
            continue

        # Write updates into the real (writable) worksheet
        ws_manips.cell(row=r_manips, column=col_status).value  = "à faire"
        ws_manips.cell(row=r_manips, column=col_targets).value = mrd_sys
        ws_manips.cell(row=r_manips, column=col_length).value  = sys_len
        updated += 1

    # 5) Save
    wb.save(OUTPUT_XLSX)
    print(f"Done → {OUTPUT_XLSX}")
    print(f"Updated: {updated} | Not found: {not_found} | Skipped (use for test? != yes): {skipped}")

if __name__ == "__main__":
    main()
