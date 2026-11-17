"""French reader-facing labels; preserve native evidence and source identifiers."""
import re

SHEETS = {'Inventory': 'Inventaire', 'Measurements': 'Mesures',
          'Comparisons': 'Comparaisons', 'Controls': 'Témoins', 'Overdue': 'Retards'}
HEADERS = {
    'Specimen': 'tissue', 'Center': 'Centre', 'Timepoint': 'Timepoint',
    'Patients': 'Patients', 'Inventory samples': 'Échantillons inventoriés',
    'Received': 'Reçus', 'Marked missing': 'Signalés manquants', 'Unassessed': 'Non évalués',
    'Overdue': 'Hors délai', 'Extracted': 'Extraits', 'Receipt rate': 'Taux de réception',
    'Due received': 'Reçus éligibles au taux', 'Timed denominator': 'Dénominateur planifié',
    'Measurement': 'Mesure', 'DNA label': "Type d'ADN", 'Unit': 'Unité',
    'Measured samples': 'Échantillons mesurés', 'Missing samples': 'Mesure indisponible',
    'Median': 'Médiane', 'Mean': 'Moyenne', 'SD': 'Écart-type',
    'Available patients': 'Patients avec mesure', 'Received samples': 'Échantillons reçus',
    'Cohort': 'Cohorte', 'Comparison': 'Comparaison', 'Matched pairs': 'Paires appariées',
    'Median 1': 'Médiane 1', 'Median 2': 'Médiane 2', 'Raw p': 'p brute',
    'Holm p': 'p ajustée (Holm)', 'Stars': 'Significativité', 'Status': 'Statut',
    'Reason': 'Motif', 'Method': 'Méthode', 'Family size': 'Nombre de tests de la famille',
    'Control records': 'Échantillons témoins', 'Source worksheet': 'Feuille source',
    'Source row': 'Ligne source', 'Issue': 'Anomalie', 'Occurrences': 'Occurrences',
}
LABELS = {
    'All specimens': 'Tous les échantillons', 'All centers': 'Tous les centres',
    'All timepoints': 'Tous les temps', 'Unknown': 'Inconnu',
    'Diagnosis': 'Diagnostic', 'Control': 'Témoin', 'Controls': 'Témoins',
    'plasma': 'plasma', 'CSF': 'LCR', 'blood pellet': 'culot sanguin', 'bone marrow': 'moelle osseuse',
    'Received': 'Reçu', 'Marked missing': 'Signalé manquant', 'Unassessed': 'Non évalué',
    'Late': 'En retard', 'Not recorded': 'Non renseigné',
    'complete': 'terminé', 'blocked': 'bloqué', 'unavailable': 'indisponible',
    'computed': 'calculé', 'retrospective': 'rétrospective', 'pooled': 'cohortes regroupées',
    'circall': 'CIRCALL', 'No applicable observations': 'Aucune observation applicable',
    'No overdue samples': 'Aucun échantillon hors délai',
    'Blocked: see Inventory for reasons': "Bloqué : consulter l'onglet Inventaire pour les motifs",
    'Control inventory': 'Inventaire des témoins', 'Control measurements': 'Mesures des témoins',
    'Available specimen volume': "Volume disponible de l'échantillon",
    'Elution volume': "Volume d'élution", 'DNA concentration': "Concentration d'ADN",
    'DNA total amount': "Quantité totale d'ADN", 'DNA per mL plasma': 'ADN par mL de plasma',
    'cfDNA fraction': 'Fraction de cfDNA', 'cfDNA concentration': 'Concentration de cfDNA',
    'cfDNA total amount': 'Quantité totale de cfDNA', 'cfDNA per mL plasma': 'cfDNA par mL de plasma',
    'cfDNA average fragment size': 'Taille moyenne des fragments de cfDNA',
    'ng/mL plasma': 'ng/mL de plasma', 'bp': 'pb', 'Invalid value': 'Valeur invalide',
    'No matched patients': 'Aucun patient apparié', 'Missing comparison group': 'Groupe de comparaison absent',
    'All paired differences are zero': 'Toutes les différences appariées sont nulles',
    'all differences zero': 'toutes les différences sont nulles',
    'exact permutation': 'permutation exacte', 'Monte Carlo permutation': 'permutation de Monte-Carlo',
    'Mann–Whitney U': 'U de Mann–Whitney', 'Wilcoxon signed-rank': 'Wilcoxon des rangs signés',
}
NOTES = {
    'Inventory': "Les lignes globales, par centre et par échantillon/temps se recoupent. Hors délai comprend les échantillons en retard et ceux signalés manquants après échéance. Taux = reçus éligibles / (reçus éligibles + signalés manquants après échéance). Les retards non confirmés manquants sont exclus du taux. Dénominateurs en colonnes masquées.",
    'Measurements': "Échantillons reçus uniquement. Zéros conservés. Q1–Q3 délimitent les 50 % centraux. Le type d'ADN est une métadonnée enregistrée. Statistiques complémentaires en colonnes masquées et dans Reference.",
    'Comparisons': "Une médiane par participant et par temps. Témoins : U de Mann–Whitney indépendant. Temps des patients : Wilcoxon apparié. La correction de Holm porte sur tous les tests planifiés. Les tests regroupés combinent les cohortes.",
    'Controls': "Les témoins sont exclus des effectifs descriptifs des patients. Leurs tests de comparaison approuvés figurent dans Comparaisons.",
    'Overdue': "En retard : délai dépassé sans mention explicite na. Signalé manquant : délai dépassé avec mention explicite na. Les retards apparaissent en premier. Filtrer Statut pour le suivi. Seuls les pseudonymes autorisés des patients figurent ici.",
}


def translate_label(value):
    if value in LABELS:
        return LABELS[value]
    if ' vs ' in value:
        return ' vs '.join(translate_label(part) for part in value.split(' vs '))
    if re.fullmatch(r'D(?:4|8|15)', value, re.I):
        return 'J'+value[1:]
    if re.fullmatch(r'TP[12] \(D\d+\)', value):
        return value.replace('(D', '(J')
    if re.fullmatch(r'Requires at least \d+ participants per group', value):
        return f"Au moins {value.split()[3]} participants par groupe requis"
    if re.fullmatch(r'Requires at least \d+ matched pairs', value):
        return f"Au moins {value.split()[3]} paires appariées requises"
    return value


def translate_status(status):
    status = status.replace('Status: ', 'Statut : ').replace(' | Assessment: ', ' | Évaluation : ')
    for source, target in [('complete','terminé'),('blocked','bloqué'),('Unavailable','Indisponible')]:
        status = status.replace(source, target)
    return status


def localize_workbook(book):
    """Translate only presentation cells; keep Reference and pseudonyms verbatim."""
    from openpyxl.utils.cell import range_boundaries
    for sheet in book:
        name = sheet.title
        if name not in SHEETS:
            continue
        # Identify table headers before changing their labels.
        headers = set()
        protected = set()
        for table in sheet.tables.values():
            left, top, right, bottom = range_boundaries(table.ref)
            for column in range(left, right+1):
                headers.add((top, column))
                if sheet.cell(top, column).value in ('Patient', 'Source worksheet', 'Source row'):
                    protected.update((row, column) for row in range(top+1, bottom+1))
        sheet.title = SHEETS[name]
        sheet.cell(1, 1, f'CIRCALL · {sheet.title}')
        status = sheet.cell(2, 1).value
        status = translate_status(status)
        sheet.cell(2, 1, status)
        sheet.cell(3, 1, NOTES[name])
        for row in sheet.iter_rows(min_row=4):
            for cell in row:
                if not isinstance(cell.value, str) or (cell.row, cell.column) in protected:
                    continue
                cell.value = (HEADERS.get(cell.value, cell.value) if (cell.row, cell.column) in headers
                              else translate_label(cell.value))
                cell.data_type = 's'
        # Existing tables have the same columns, ranges and names.
        for table in sheet.tables.values():
            for column in table.tableColumns:
                column.name = HEADERS.get(column.name, column.name)
        # French labels are longer. Only affected columns/header/note rows expand.
        for row, column in headers:
            cell = sheet.cell(row, column)
            letter = cell.column_letter
            sheet.column_dimensions[letter].width = max(sheet.column_dimensions[letter].width,
                                                       min(34, len(cell.value)+2))
            sheet.row_dimensions[row].height = 44
        sheet.row_dimensions[3].height = 56
