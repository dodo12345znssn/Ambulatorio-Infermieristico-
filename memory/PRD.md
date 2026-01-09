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

### Sessione 09/01/2026 - Update 6

#### Assistente IA Integrato
- **Chat IA** accessibile da pulsante floating blu in basso a destra
- **Funzionalità complete**:
  - Creare pazienti: "Crea paziente PICC nome Mario cognome Rossi"
  - Prendere appuntamenti: "Dai appuntamento a Mario Rossi per giovedì 22 alle 9:00"
  - Consultare statistiche: "Quante medicazioni ho fatto nel 2026?"
  - Compilare schede impianto: "Crea scheda impianto per Rossi con data 12/12/25 e tipo PICC"
  - Aprire cartelle: "Apri cartella paziente Rossi"
  - Cercare pazienti: "Cerca paziente Rossi"
- **Comandi a step**: Possibilità di dare comandi incrementali
- **Comandi complessi**: Un unico messaggio per azioni multiple
- **Gestione orari**: Se orario occupato, propone primo disponibile
- **Cronologia chat**: Possibilità di vedere chat precedenti e eliminarle
- **Nuova chat**: Pulsante + per iniziare nuova conversazione
- **Comando vocale**: Pulsante microfono per dettatura (Web Speech API)
- **Sintesi vocale**: Pulsante "Ascolta" per ascoltare le risposte dell'IA
- **Powered by**: OpenAI GPT-4o con Emergent LLM Key

### Sessione 08/01/2026 - Update 5

#### Statistiche Annuali
- Aggiunta possibilità di visualizzare statistiche per **tutto l'anno**
- Nel selettore del mese, la prima opzione è ora "Tutto l'anno"
- Permette confronti annuali: es. **Anno 2025** vs **Anno 2026**
- Funziona sia per statistiche MED/PICC che per Impianti
- Export PDF e Excel aggiornati per supportare il periodo annuale

### Sessione 08/01/2026 - Update 4

#### Stampa PDF Scheda Impianto Completa - Allineamento con Frontend
- **RIMOSSO**: Campo "Lotto" dalla stampa
- **RIMOSSO**: Sezione "POSIZIONAMENTO CVC" (succlavia dx/sn, giugulare dx/sn)
- **RIMOSSO**: Label "POSIZIONAMENTO PICC"
- **AGGIORNATO**: Sezione posizionamento ora mostra solo:
  - BRACCIO: dx / sn
  - VENA: Basilica / Cefalica / Brachiale / Altro (con nota se specificata)
- La stampa PDF ora riflette esattamente la scheda impianto completa del frontend

### Sessione 08/01/2026 - Update 3

#### Scheda Gestione PICC - Copia Automatica Medicazione Precedente
- Quando si aggiunge un nuovo giorno alla scheda mensile, i dati vengono copiati automaticamente dalla medicazione precedente
- La data viene sempre aggiornata al nuovo giorno
- L'utente può comunque modificare tutti i campi
- Messaggio di conferma "Dati copiati dalla medicazione precedente"

#### Scheda Impianto PICC Semplificata - Nuovi Campi
- Aggiunto campo "Lunghezza Totale Catetere" (cm) - es. 25 cm
- Aggiunto campo "Lunghezza Impiantata" (cm) - es. 21 cm
- Aggiunta opzione "Altro" per la vena con campo note

#### Scheda Impianto PICC Completa - Semplificazione
- **RIMOSSO**: Campo "Lotto"
- **RIMOSSO**: Posizionamento CVC (succlavia dx/sx, giugulare dx/sx)
- **RIMOSSO**: Label "PICC" nel posizionamento
- **AGGIORNATO**: Posizionamento ora include solo:
  - Braccio: dx / sn
  - Vena: Basilica / Cefalica / Brachiale / Altro (con campo note)

### Sessione 08/01/2026 - Update 2

#### Statistiche - Esclusione Pazienti Non Presentati
- Le prestazioni dei pazienti segnati in rosso (stato `non_presentato`) vengono automaticamente escluse dalle statistiche
- Il conteggio di accessi, pazienti unici e prestazioni considera solo gli appuntamenti effettuati o da_fare
- Questa logica si applica sia alle statistiche MED/PICC che al dettaglio mensile

#### Agenda - Pre-selezione Prestazioni PICC
- Quando si aggiunge un appuntamento PICC per un paziente PICC o PICC_MED
- Le prestazioni "Medicazione semplice" e "Irrigazione catetere" vengono pre-selezionate automaticamente
- L'utente può comunque deselezionare una delle due prestazioni prima di confermare

### Sessione 08/01/2026 - Update 1

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
