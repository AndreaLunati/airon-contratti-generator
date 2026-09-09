import os
import json
import io
import streamlit as st
import fitz  # PyMuPDF
from openai import OpenAI
from datetime import datetime, timedelta

st.set_page_config(
    page_title="Generatore Contratto Airon Marine",
    page_icon="🚤",
    layout="centered"
)

# --- 1. CONFIGURAZIONE SICUREZZA (SECRETS E PASSWORD) ---
if "OPENAI_API_KEY" in st.secrets:
    os.environ["OPENAI_API_KEY"] = st.secrets["OPENAI_API_KEY"]

def check_password():
    def password_entered():
        if st.session_state["password"] == st.secrets["APP_PASSWORD"]:
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.text_input("🔑 Inserisci la password per accedere al gestionale", type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["password_correct"]:
        st.text_input("🔑 Inserisci la password per accedere al gestionale", type="password", on_change=password_entered, key="password")
        st.error("😕 Password errata. Riprova.")
        return False
    else:
        return True

if not check_password():
    st.stop()

# --- INTERFACCIA APPLICAZIONE ---
st.title("🚤 Compilatore Automatico Contratto Airon Marine")
st.write("Estrai i dati, controllali e modificali se necessario prima di generare il PDF.")

col1, col2 = st.columns(2)
with col1:
    uploaded_contratto = st.file_uploader("1. Documento di Prenotazione (PDF)", type=["pdf"])
with col2:
    uploaded_fattura = st.file_uploader("2. Modello Contratto Vuoto (PDF)", type=["pdf"])

st.markdown("---")

def estrai_testo_da_pdf(file_pdf):
    testo = ""
    file_pdf.seek(0)
    with fitz.open(stream=file_pdf.read(), filetype="pdf") as doc:
        for pagina in doc:
            testo += pagina.get_text()
    return testo

def estrai_dati_con_ai(testo_contratto):
    client = OpenAI()
    prompt = f"""
    Analizza il seguente testo estratto da un documento di prenotazione e restituisci un JSON puro con questi campi chiave:
    - cliente (Nome e Cognome)
    - indirizzo (se non presente, stringa vuota "")
    - email (se non presente, stringa vuota "")
    - telefono (se non presente, stringa vuota "")
    - patente_nautica (se non presente, stringa vuota "")
    - hotel (RESTITUISCI STRINGA VUOTA "" se non viene menzionato un hotel o struttura specifica)
    - numero_prenotazione
    - barca (DEVE ESSERE ESATTAMENTE UNA di queste stringhe: "MARINELLO 18.1", "MARINELLO 18.2", "MARINELLO 18.3", "MARINELLO 18.4", "SONCOR 21", "AIRON 223", "AIRON 277 FISH", "MASTER F. 279", "KONDOR 810", "AIRON 325". Se nel testo trovi "Marinello 18" generico, metti "MARINELLO 18.1").
    - data (formato DD/MM/YYYY)
    - ora_partenza (formato HH:MM)
    - ora_arrivo (formato HH:MM)
    - durata
    - partecipanti
    - valore_prenotazione

    Testo del documento:
    {testo_contratto}
    """
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        response_format={ "type": "json_object" },
        messages=[
            {"role": "system", "content": "Sei un assistente per l'estrazione precisa di dati."},
            {"role": "user", "content": prompt}
        ]
    )
    return response.choices[0].message.content

def calcola_ora_arrivo(ora_partenza_str, durata_str):
    try:
        ore_durata = int(''.join(filter(str.isdigit, durata_str)) or 5)
        dt_partenza = datetime.strptime(ora_partenza_str.strip()[:5], "%H:%M")
        dt_arrivo = dt_partenza + timedelta(hours=ore_durata)
        return dt_arrivo.strftime("%H:%M")
    except:
        return "18:30"

def compila_contratto_coordinate(file_fattura_vuota, dati):
    file_fattura_vuota.seek(0)
    doc = fitz.open(stream=file_fattura_vuota.read(), filetype="pdf")
    pagina = doc[0]
    
    ora_partenza = dati.get('ora_partenza', '10:00')
    durata = dati.get('durata', '5 ore')
    ora_arrivo = dati.get('ora_arrivo') or calcola_ora_arrivo(ora_partenza, durata)

    testi_da_scrivere = [
        (dati.get('data', ''), 70, 150, 10),
        (ora_partenza, 310, 150, 10),
        (ora_arrivo, 515, 150, 10),
        
        (dati.get('cliente', ''), 220, 350, 10),
        (dati.get('indirizzo', ''), 85, 370, 10),
        (dati.get('patente_nautica', ''), 140, 525, 10),
        (dati.get('telefono', ''), 100, 467, 10),
        (dati.get('email', ''), 370, 467, 10),
        (dati.get('hotel', ''), 100, 550, 10),
        
        (str(dati.get('partecipanti', '')), 257, 580, 10),
        (str(durata), 305, 600, 10),
        (str(dati.get('valore_prenotazione', '')), 275, 620, 10)
    ]

    for testo, x, y, dim_font in testi_da_scrivere:
        if testo:
            pagina.insert_text(fitz.Point(x, y), str(testo), fontsize=dim_font, color=(0, 0, 0))

    barca_trovata = dati.get('barca', '').strip()
    if barca_trovata:
        risultati_barca = pagina.search_for(barca_trovata)
        if risultati_barca:
            r_barca = risultati_barca[0]
            punto_flag = fitz.Point(r_barca.x0 - 15, r_barca.y1 - 2)
            pagina.insert_text(punto_flag, "X", fontsize=11, color=(0, 0, 0))

    pdf_bytes = doc.write()
    doc.close()
    return pdf_bytes

if "dati_estratti" not in st.session_state:
    st.session_state.dati_estratti = None

# --- FASE 1: ESTRAZIONE DATI ---
if st.button("🔍 1. Estrai Dati dalla Prenotazione", type="primary"):
    if uploaded_contratto:
        with st.spinner("Estrazione con intelligenza artificiale in corso..."):
            try:
                testo_contratto = estrai_testo_da_pdf(uploaded_contratto)
                json_risposta = estrai_dati_con_ai(testo_contratto)
                st.session_state.dati_estratti = json.loads(json_risposta)
                st.success("Dati estratti con successo! Controllali qui sotto e modificali se necessario.")
            except Exception as e:
                st.error(f"Errore durante l'estrazione: {e}")
    else:
        st.session_state.dati_estratti = {
            "cliente": "Mario Rossi",
            "indirizzo": "Via Roma 10, Milano",
            "email": "mario.rossi@example.com",
            "telefono": "+39 333 1234567",
            "patente_nautica": "",
            "hotel": "",
            "numero_prenotazione": "TEST-001",
            "barca": "MARINELLO 18.1",
            "data": "10/06/2026",
            "ora_partenza": "09:30",
            "ora_arrivo": "15:30",
            "durata": "5 ore",
            "partecipanti": 4,
            "valore_prenotazione": "250.00"
        }
        st.info("ℹ️ Nessun file di prenotazione caricato: caricati dati di esempio.")

# --- FASE 2: MODIFICA MANUALE E GENERAZIONE PDF ---
if st.session_state.dati_estratti:
    st.markdown("---")
    st.subheader("✏️ 2. Verifica e Modifica i Dati prima di Stampare")
    st.write("Modifica direttamente nei box sottostanti qualsiasi campo errato o vuoto:")

    d = st.session_state.dati_estratti

    col_a, col_b = st.columns(2)
    with col_a:
        cliente_edit = st.text_input("Cliente", value=d.get("cliente", ""))
        indirizzo_edit = st.text_input("Indirizzo", value=d.get("indirizzo", ""))
        email_edit = st.text_input("Email", value=d.get("email", ""))
        telefono_edit = st.text_input("Telefono", value=d.get("telefono", ""))
        patente_edit = st.text_input("Patente Nautica", value=d.get("patente_nautica", ""))
        hotel_edit = st.text_input("Hotel / B&B (lascia vuoto se assente)", value=d.get("hotel", ""))

    with col_b:
        lista_barche = [
            "MARINELLO 18.1", "MARINELLO 18.2", "MARINELLO 18.3", "MARINELLO 18.4", 
            "SONCOR 21", "AIRON 223", "AIRON 277 FISH", "MASTER F. 279", "KONDOR 810", "AIRON 325"
        ]
        barca_attuale = d.get("barca", "MARINELLO 18.1")
        if barca_attuale not in lista_barche:
            lista_barche.insert(0, barca_attuale)
            
        barca_edit = st.selectbox("Barca", options=lista_barche, index=lista_barche.index(barca_attuale) if barca_attuale in lista_barche else 0)
        data_edit = st.text_input("Data", value=d.get("data", ""))
        ora_p_edit = st.text_input("Ora Partenza", value=d.get("ora_partenza", ""))
        ora_a_edit = st.text_input("Ora Arrivo", value=d.get("ora_arrivo", ""))
        durata_edit = st.text_input("Durata", value=d.get("durata", ""))
        partecipanti_edit = st.text_input("Partecipanti", value=str(d.get("partecipanti", "")))
        prezzo_edit = st.text_input("Valore Prenotazione", value=str(d.get("valore_prenotazione", "")))

    if st.button("🚀 3. Genera e Scarica Contratto PDF", type="primary"):
        if uploaded_fattura:
            dati_finali = {
                "cliente": cliente_edit,
                "indirizzo": indirizzo_edit,
                "email": email_edit,
                "telefono": telefono_edit,
                "patente_nautica": patente_edit,
                "hotel": hotel_edit,
                "barca": barca_edit,
                "data": data_edit,
                "ora_partenza": ora_p_edit,
                "ora_arrivo": ora_a_edit,
                "durata": durata_edit,
                "partecipanti": partecipanti_edit,
                "valore_prenotazione": prezzo_edit
            }
            
            uploaded_fattura.seek(0)
            pdf_compilato_bytes = compila_contratto_coordinate(uploaded_fattura, dati_finali)
            
            st.success("Contratto compilato con successo!")
            st.download_button(
                label="📥 Scarica PDF Compilato",
                data=pdf_compilato_bytes,
                file_name=f"contratto_{cliente_edit.replace(' ', '_')}.pdf",
                mime="application/pdf"
            )
        else:
            st.warning("Per favore carica il Modello Contratto Vuoto (PDF) nella colonna di destra prima di generare il file.")