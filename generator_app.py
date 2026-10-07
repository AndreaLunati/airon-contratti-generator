import os
import json
import io
import re
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
        st.text_input(
            "🔑 Inserisci la password per accedere al gestionale",
            type="password",
            on_change=password_entered,
            key="password"
        )
        return False
    elif not st.session_state["password_correct"]:
        st.text_input(
            "🔑 Inserisci la password per accedere al gestionale",
            type="password",
            on_change=password_entered,
            key="password"
        )
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
    uploaded_contratto = st.file_uploader(
        "1. Documento di Prenotazione (PDF)",
        type=["pdf"]
    )

with col2:
    uploaded_fattura = st.file_uploader(
        "2. Modello Contratto Vuoto (PDF)",
        type=["pdf"]
    )

st.subheader("Carta d'identità (opzionale)")
col_doc1, col_doc2 = st.columns(2)

with col_doc1:
    documento_fronte = st.file_uploader(
        "📷 Carta d'identità - Fronte",
        type=["jpg", "jpeg", "png"],
        key="documento_fronte"
    )

with col_doc2:
    documento_retro = st.file_uploader(
        "📷 Carta d'identità - Retro",
        type=["jpg", "jpeg", "png"],
        key="documento_retro"
    )

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
    Analizza il seguente testo estratto da un documento di prenotazione
    e restituisci un JSON puro con questi campi chiave:

    - cliente (Nome e Cognome)
- email (se non presente, stringa vuota "")
- telefono (se non presente, stringa vuota "")

- documento:
  estrai il numero del documento di identità del cliente.
  Può essere indicato come "documento", "documento d'identità",
  "carta d'identità", "ID", "ID number", "numero documento",
  "document number" o diciture simili.
  Restituisci SOLO il numero/codice del documento.
  Se non presente, restituisci stringa vuota "".

- patente_nautica:
  estrai il numero della patente nautica del cliente.
  Può essere indicato come "patente nautica", "patente",
  "numero patente", "license", "boat license",
  "nautical license", "licence number" o diciture simili.
  Restituisci SOLO il numero/codice della patente.
  Se non presente, restituisci stringa vuota "".

- hotel (RESTITUISCI STRINGA VUOTA "" se non viene menzionato un hotel o struttura specifica)
    - numero_prenotazione
    - barca (DEVE ESSERE ESATTAMENTE UNA di queste stringhe:
      "MARINELLO 18.1", "MARINELLO 18.2", "MARINELLO 18.3", "MARINELLO 18.4",
      "SONCOR 21", "AIRON 223", "AIRON 277 FISH", "MASTER F. 279",
      "KONDOR 810", "AIRON 325".
      Se nel testo trovi "Marinello 18" generico, metti "MARINELLO 18.1").
    - data (formato DD/MM/YYYY)
    - ora_partenza (formato HH:MM)
    - durata
    - partecipanti
    - valore_prenotazione

    NON serve estrarre l'ora di arrivo: verrà calcolata automaticamente
    usando ora_partenza + durata.

    Testo del documento:
    {testo_contratto}
    """

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": "Sei un assistente per l'estrazione precisa di dati."
            },
            {
                "role": "user",
                "content": prompt
            }
        ]
    )

    return response.choices[0].message.content


def calcola_ora_arrivo(ora_partenza_str, durata_str):
    """
    Calcola l'ora di arrivo partendo da ora di partenza + durata.
    Supporta ad esempio:
    - 3 ore
    - 5 ore
    - 3h
    - 3:30
    - 3 ore 30 minuti
    - 3,5 ore
    """
    try:
        ora_partenza_str = str(ora_partenza_str).strip()

        # Accetta anche "12" oltre a "12:00"
        if re.fullmatch(r"\d{1,2}", ora_partenza_str):
            ora_partenza_str += ":00"

        dt_partenza = datetime.strptime(
            ora_partenza_str[:5],
            "%H:%M"
        )

        durata_testo = str(durata_str).lower().strip()
        ore = 0
        minuti = 0

        # Caso 3:30
        match_hhmm = re.search(r"(\d+)\s*:\s*(\d+)", durata_testo)
        if match_hhmm:
            ore = int(match_hhmm.group(1))
            minuti = int(match_hhmm.group(2))
        else:
            # Caso 3,5 / 3.5 ore
            match_decimale = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:ore|ora|h)?", durata_testo)
            if match_decimale:
                valore = float(match_decimale.group(1).replace(",", "."))
                ore = int(valore)
                minuti = round((valore - ore) * 60)

            # Se sono indicati esplicitamente i minuti, usali
            match_minuti = re.search(r"(\d+)\s*(?:minuti|min|m)\b", durata_testo)
            if match_minuti:
                minuti = int(match_minuti.group(1))

        dt_arrivo = dt_partenza + timedelta(hours=ore, minutes=minuti)
        return dt_arrivo.strftime("%H:%M")

    except Exception:
        return ""


def compila_contratto_coordinate(file_fattura_vuota, dati):
    file_fattura_vuota.seek(0)
    doc = fitz.open(
        stream=file_fattura_vuota.read(),
        filetype="pdf"
    )

    pagina = doc[0]

    ora_partenza = dati.get("ora_partenza", "10:00")
    durata = dati.get("durata", "5 ore")

    # MODIFICA: l'ora di arrivo viene SEMPRE calcolata.
    ora_arrivo = calcola_ora_arrivo(ora_partenza, durata)

    barca_trovata = dati.get("barca", "").strip()
    marinello = barca_trovata.startswith("MARINELLO 18")

    # Per le barche con patente usiamo la patente come documento.
    # Per Marinello resta l'eventuale documento d'identità.
    documento_da_scrivere = ""
    patente_da_scrivere = ""

    if marinello:
        documento_da_scrivere = dati.get("documento", "")
    else:
        documento_da_scrivere = ""

    # Se il campo patente è compilato, stampalo sempre nella sua posizione.
    patente_da_scrivere = dati.get("patente_nautica", "").strip()

    testi_da_scrivere = [
        (dati.get("data", ""), 70, 150, 10),
        (ora_partenza, 310, 150, 10),
        (ora_arrivo, 515, 150, 10),

        (dati.get("cliente", ""), 220, 350, 10),
        ("La Fornace 78, Lezzeno, Airon Marine sede", 100, 375, 10),

        # Documento / patente
        (documento_da_scrivere, 300, 395, 10),
        (patente_da_scrivere, 115, 415, 10),

        (dati.get("telefono", ""), 100, 467, 10),
        (dati.get("email", ""), 370, 467, 10),
        (dati.get("hotel", ""), 100, 550, 10),

        (str(dati.get("partecipanti", "")), 257, 580, 10),
        (str(durata), 305, 600, 10),
        (str(dati.get("valore_prenotazione", "")), 275, 620, 10)
    ]

    for testo, x, y, dim_font in testi_da_scrivere:
        if testo:
            pagina.insert_text(
                fitz.Point(x, y),
                str(testo),
                fontsize=dim_font,
                color=(0, 0, 0)
            )

    # X della barca: coordinate centrate e scalate in base al modello.
    # Il centro della X di MARINELLO 18.1 è x=23, y=215.
    # Le altre righe scalano verticalmente con lo stesso passo del contratto.
    coordinate_x_barche = {
        "MARINELLO 18.1": (23, 215),
        "MARINELLO 18.2": (23, 230),
        "MARINELLO 18.3": (23, 245),
        "MARINELLO 18.4": (23, 260),
        "SONCOR 21": (209, 215),
        "AIRON 223": (209, 237),
        "AIRON 277 FISH": (407, 237),
        "MASTER F. 279": (407, 260),
        "KONDOR 810": (407, 284),
        "AIRON 325": (407, 307),
    }

    if barca_trovata in coordinate_x_barche:
        x_barca, y_barca = coordinate_x_barche[barca_trovata]
        # insert_text usa la baseline: piccolo offset per centrare visivamente la X.
        pagina.insert_text(
            fitz.Point(x_barca - 3.5, y_barca + 4),
            "X",
            fontsize=11,
            color=(0, 0, 0)
        )

    # Carburante sempre incluso.
    # Centro richiesto della X: x=233, y=657.
    pagina.insert_text(
        fitz.Point(233 - 3.5, 657 + 4),
        "X",
        fontsize=11,
        color=(0, 0, 0)
    )

    pdf_bytes = doc.write()
    doc.close()

    return pdf_bytes


def aggiungi_carta_identita_a4(pdf_contratto_bytes, fronte=None, retro=None):
    """
    Se è presente almeno una foto, aggiunge UNA sola pagina A4 al PDF.
    Fronte e retro vengono disposti uno sopra l'altro, centrati,
    senza deformazioni e mantenendo le proporzioni originali.
    """
    if fronte is None and retro is None:
        return pdf_contratto_bytes

    pdf_finale = fitz.open(stream=pdf_contratto_bytes, filetype="pdf")
    pagina = pdf_finale.new_page(width=595, height=842)  # A4

    # Titolo della pagina.
    pagina.insert_text(
        fitz.Point(40, 45),
        "Carta d'identità",
        fontsize=14,
        color=(0, 0, 0)
    )

    def inserisci_foto(uploaded_file, area):
        if uploaded_file is None:
            return

        contenuto = uploaded_file.getvalue()
        img_doc = fitz.open(stream=contenuto)
        pix = img_doc[0].get_pixmap(alpha=False)
        img_doc.close()

        rapporto_img = pix.width / pix.height
        rapporto_area = area.width / area.height

        if rapporto_img > rapporto_area:
            larghezza = area.width
            altezza = larghezza / rapporto_img
        else:
            altezza = area.height
            larghezza = altezza * rapporto_img

        x0 = area.x0 + (area.width - larghezza) / 2
        y0 = area.y0 + (area.height - altezza) / 2
        rect = fitz.Rect(x0, y0, x0 + larghezza, y0 + altezza)

        pagina.insert_image(
            rect,
            stream=contenuto,
            keep_proportion=True
        )

    # Due aree ampie sulla stessa pagina A4.
    area_fronte = fitz.Rect(40, 70, 555, 430)
    area_retro = fitz.Rect(40, 450, 555, 810)

    inserisci_foto(fronte, area_fronte)
    inserisci_foto(retro, area_retro)

    output = io.BytesIO()
    pdf_finale.save(output)
    pdf_finale.close()
    return output.getvalue()


if "dati_estratti" not in st.session_state:
    st.session_state.dati_estratti = None


# --- FASE 1: ESTRAZIONE DATI ---
if st.button(
    "🔍 1. Estrai Dati dalla Prenotazione",
    type="primary"
):
    if uploaded_contratto:
        with st.spinner(
            "Estrazione con intelligenza artificiale in corso..."
        ):
            try:
                testo_contratto = estrai_testo_da_pdf(
                    uploaded_contratto
                )

                json_risposta = estrai_dati_con_ai(
                    testo_contratto
                )

                st.session_state.dati_estratti = json.loads(
                    json_risposta
                )

                st.success(
                    "Dati estratti con successo! "
                    "Controllali qui sotto e modificali se necessario."
                )

            except Exception as e:
                st.error(
                    f"Errore durante l'estrazione: {e}"
                )
    else:
        st.session_state.dati_estratti = {
            "cliente": "Mario Rossi",
            "indirizzo": "Via Roma 10, Milano",
            "email": "mario.rossi@example.com",
            "telefono": "+39 333 1234567",
            "documento": "",
            "patente_nautica": "",
            "hotel": "",
            "numero_prenotazione": "TEST-001",
            "barca": "MARINELLO 18.1",
            "data": "10/06/2026",
            "ora_partenza": "09:30",
            "durata": "5 ore",
            "partecipanti": 4,
            "valore_prenotazione": "250.00"
        }

        st.info(
            "ℹ️ Nessun file di prenotazione caricato: "
            "caricati dati di esempio."
        )


# --- FASE 2: MODIFICA MANUALE E GENERAZIONE PDF ---
if st.session_state.dati_estratti:
    st.markdown("---")

    st.subheader(
        "✏️ 2. Verifica e Modifica i Dati prima di Stampare"
    )

    st.write(
        "Modifica direttamente nei box sottostanti "
        "qualsiasi campo errato o vuoto:"
    )

    d = st.session_state.dati_estratti

    col_a, col_b = st.columns(2)

    with col_a:
        cliente_edit = st.text_input(
            "Cliente",
            value=d.get("cliente", "")
        )

        email_edit = st.text_input(
            "Email",
            value=d.get("email", "")
        )

        telefono_edit = st.text_input(
            "Telefono",
            value=d.get("telefono", "")
        )

        documento_edit = st.text_input(
            "N° Documento d'identità",
            value=d.get("documento", "")
        )

        patente_edit = st.text_input(
            "Patente Nautica",
            value=d.get("patente_nautica", "")
        )

        hotel_edit = st.text_input(
            "Hotel / B&B (lascia vuoto se assente)",
            value=d.get("hotel", "")
        )

        st.text_input(
            "Luogo di partenza",
            value="Via Fornace 78, 22025 Lezzeno (CO) - Airon Marine",
            disabled=True
        )

        st.text_input(
            "Carburante",
            value="INCLUSO",
            disabled=True
        )

    with col_b:
        # Il valore interno resta quello originale per non rompere
        # la ricerca della barca nel PDF. La targa viene mostrata
        # solamente nella selectbox.
        targhe = {
            "MARINELLO 18.1": "1801",
            "MARINELLO 18.2": "1802",
            "MARINELLO 18.3": "0655 CO",
            "MARINELLO 18.4": "0526 CO"
        }

        lista_barche = [
            "MARINELLO 18.1",
            "MARINELLO 18.2",
            "MARINELLO 18.3",
            "MARINELLO 18.4",
            "SONCOR 21",
            "AIRON 223",
            "AIRON 277 FISH",
            "MASTER F. 279",
            "KONDOR 810",
            "AIRON 325"
        ]

        barca_attuale = d.get(
            "barca",
            "MARINELLO 18.1"
        )

        if barca_attuale not in lista_barche:
            lista_barche.insert(
                0,
                barca_attuale
            )

        def mostra_barca(nome):
            if nome in targhe:
                return f"{nome} - targa {targhe[nome]}"
            return nome

        barca_edit = st.selectbox(
            "Barca",
            options=lista_barche,
            index=lista_barche.index(barca_attuale)
            if barca_attuale in lista_barche
            else 0,
            format_func=mostra_barca
        )

        data_edit = st.text_input(
            "Data",
            value=d.get("data", "")
        )

        ora_p_edit = st.text_input(
            "Ora Partenza",
            value=d.get("ora_partenza", "")
        )

        durata_edit = st.text_input(
            "Durata",
            value=d.get("durata", "")
        )

        # MODIFICA: ora di arrivo automatica.
        ora_a_edit = calcola_ora_arrivo(
            ora_p_edit,
            durata_edit
        )

        st.text_input(
            "Ora Arrivo (automatica)",
            value=ora_a_edit,
            disabled=True
        )

        partecipanti_edit = st.text_input(
            "Partecipanti",
            value=str(d.get("partecipanti", ""))
        )

        prezzo_edit = st.text_input(
            "Valore Prenotazione",
            value=str(d.get("valore_prenotazione", ""))
        )

    # Informazione sulla patente in base alla barca selezionata.
    if barca_edit.startswith("MARINELLO 18"):
        st.info(
            "ℹ️ Per il Marinello 18 la patente nautica non è necessaria."
        )
    else:
        st.info(
            "ℹ️ Per questa barca è obbligatoria la patente nautica. "
            "Se presente, nel contratto verrà utilizzata la patente "
            "senza compilare anche il documento d'identità."
        )

    if st.button(
        "🚀 3. Genera e Scarica Contratto PDF",
        type="primary"
    ):
        if uploaded_fattura:

            # Patente obbligatoria per tutte le barche
            # tranne i Marinello 18.
            if (
                not barca_edit.startswith("MARINELLO 18")
                and not patente_edit.strip()
            ):
                st.error(
                    "⚠️ Per la barca selezionata è obbligatorio "
                    "inserire il numero della patente nautica."
                )

            else:
                dati_finali = {
                    "cliente": cliente_edit,
                    "email": email_edit,
                    "telefono": telefono_edit,
                    "documento": documento_edit,
                    "patente_nautica": patente_edit,
                    "hotel": hotel_edit,
                    "barca": barca_edit,
                    "data": data_edit,
                    "ora_partenza": ora_p_edit,
                    "ora_arrivo": ora_a_edit,
                    "durata": durata_edit,
                    "partecipanti": partecipanti_edit,
                    "valore_prenotazione": prezzo_edit,
                    "luogo_partenza": (
                        "Via Fornace 78, 22025 Lezzeno (CO) - Airon Marine"
                    ),
                    "carburante": "INCLUSO"
                }

                uploaded_fattura.seek(0)

                pdf_compilato_bytes = compila_contratto_coordinate(
                    uploaded_fattura,
                    dati_finali
                )

                # Aggiunge in coda le scansioni della carta d'identità.
                pdf_compilato_bytes = aggiungi_carta_identita_a4(
                    pdf_compilato_bytes,
                    documento_fronte,
                    documento_retro
                )

                st.success(
                    "Contratto compilato con successo!"
                )

                st.download_button(
                    label="📥 Scarica PDF Compilato",
                    data=pdf_compilato_bytes,
                    file_name=(
                        f"contratto_{cliente_edit.replace(' ', '_')}.pdf"
                    ),
                    mime="application/pdf"
                )

        else:
            st.warning(
                "Per favore carica il Modello Contratto Vuoto (PDF) "
                "nella colonna di destra prima di generare il file."
            )
