# Ambulatorio Infermieristico - PRD

## Problema Originale
Applicazione web full-stack per la gestione di un ambulatorio infermieristico con supporto per:
- Gestione pazienti (PICC e MED)
- Schede impianto e medicazione
- Agenda appuntamenti
- Generazione PDF cartelle cliniche
- Modulistica scaricabile

## Architettura
- **Backend**: FastAPI + MongoDB (pymongo)
- **Frontend**: React + Tailwind CSS + shadcn/ui
- **PDF Generation**: ReportLab

## Funzionalità Implementate

### Sessione 08/01/2026

#### Agenda - Gestione Appuntamenti Avanzata
- Nome paziente grande e visibile (font-bold text-base)
- Colorazione stato: Nero (da_fare), Verde (effettuato), Rosso (non_presentato)
- **Click singolo**: apre popup di gestione appuntamento
- **Doppio click**: naviga direttamente alla cartella clinica del paziente
- Popup di gestione con:
  - Cambio stato (Effettuato/Non Presentato)
  - Modifica prestazioni
  - Pulsante "Apri Cartella" per navigare alla cartella clinica
  - Eliminazione appuntamento

#### Stampa PDF Scheda Impianto - Aggiornata
- Nuovi tipi catetere: PICC, Midline, PICC Port, PORT a cath, Altro
- Nuovi campi misure: Diametro vena (mm), Profondità (cm), Lunghezza totale/impiantata (cm), French, Lumi, Lotto
- Nuove procedure: Colla hystoacrilica, ECG intracavitario
- Motivazioni aggiornate: NPT, Scarso patrimonio venoso
- Footer con 1° e 2° Operatore

#### Modulistica PICC Aggiornata
- Sostituito "Specifiche Impianto" con "Scheda Impianto" (nuovo PDF)
- Rinominato documenti per chiarezza

### Sessioni Precedenti
- Clonazione e setup progetto
- Form Scheda Impianto PICC (versione completa e semplificata)
- Correzione errori backend
- Rimozione sistema codici identificativi
- Miglioramento anteprima foto

## Backlog / TODO

### P1 - Importante
- Testare download PDF sezioni separate (anagrafica, medicazione, impianto, gestione)
- Implementare funzionalità ritaglio foto

### P2 - Nice to Have
- Separare "Gestione PICC" come sezione indipendente nel download

## Schema Database

### appointments
```json
{
  "id": "uuid",
  "patient_id": "uuid",
  "data": "YYYY-MM-DD",
  "ora": "HH:MM",
  "tipo": "PICC/MED",
  "prestazioni": ["array"],
  "stato": "da_fare/effettuato/non_presentato"
}
```

### schede_impianto_picc
```json
{
  "id": "uuid",
  "patient_id": "uuid",
  "scheda_type": "completa/semplificata",
  "tipo_catetere": "picc/midline/picc_port/port_a_cath/altro",
  "diametro_vena_mm": "string",
  "lunghezza_totale_cm": "string",
  "french": "string",
  "lumi": "string",
  "operatore": "string",
  "secondo_operatore": "string",
  "colla_hystoacrilica": "boolean",
  "ecg_intracavitario": "boolean"
}
```

## File Principali
- `/app/backend/server.py` - API, logica DB, generazione PDF
- `/app/frontend/src/components/SchedaImpiantoPICC.jsx` - Form scheda impianto
- `/app/frontend/src/pages/AgendaPage.jsx` - Agenda appuntamenti
- `/app/frontend/src/pages/ModulisticaPage.jsx` - Modulistica scaricabile
