import os
import re
import unicodedata
import traceback
from datetime import datetime
from collections import Counter
from threading import Timer
import webbrowser
from flask import Flask, render_template, request, jsonify, session, send_file
from flask_cors import CORS

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "mobilia-secure-key-2024")
app.config['PERMANENT_SESSION_LIFETIME'] = 3600
CORS(app)

def normalizar_mensaje(msg):
    """Limpia el mensaje para detectar duplicados, preservando acentos en espa?ol."""
    msg = msg.lower().strip()
    # Elimina emojis pero mantiene caracteres latinos con acentos
    msg = re.sub(r'[^\w\s\u00C0-\u00FF¨¢¨¦¨ª¨®¨²?¨¹]', '', msg, flags=re.UNICODE)
    # Elimina URLs y tel¨¦fonos
    msg = re.sub(r'https?://\S+|www\.\S+', '', msg)
    msg = re.sub(r'\+?\d[\d\s\-\(\)]{7,}', '', msg)
    # Unifica espacios
    msg = re.sub(r'\s+', ' ', msg).strip()
    return msg

def parsear_fecha(fecha_str):
    fecha_str = fecha_str.replace('-', '/').replace('.', '/')
    for fmt in ['%d/%m/%Y', '%d/%m/%y', '%Y/%m/%d', '%d/%m']:
        try:
            dt = datetime.strptime(fecha_str.strip(), fmt)
            if dt.year < 100:
                dt = dt.replace(year=dt.year + 2000)
            return dt
        except ValueError:
            continue
    return None

def procesar_chat(texto_chat, fecha_inicio=None, fecha_fin=None, tipo_inmueble=None):
    patron_palabras = r"\b(requiero|solicito|necesito|compro|se requiere|se necesita|se solicita|se busca)\b"
    lineas = texto_chat.split('\n')
    requerimientos_lista = []
    inmuebles_conteo = []
    agentes_lista = []
    vistos = set()
    patron_mensaje = re.compile(r"^\[?(\d{1,4}[/\-\.]\d{1,2}[/\-\.]\d{2,4}),?\s\d{1,2}:\d{2}(?::\d{2})?\]?\s(?:-\s)?([^:]+):\s(.*)$")

    for linea in lineas:
        match = patron_mensaje.match(linea.strip())
        if match:
            fecha_str, contacto, mensaje = match.groups()
            fecha_obj = parsear_fecha(fecha_str)
            
            if fecha_inicio and fecha_obj and fecha_obj < fecha_inicio:
                continue
            if fecha_fin and fecha_obj and fecha_obj > fecha_fin:
                continue

            if re.search(patron_palabras, mensaje, re.IGNORECASE):
                clave = normalizar_mensaje(mensaje)
                if clave not in vistos:
                    vistos.add(clave)

                    msg_lower = mensaje.lower()
                    tipo_detectado = "Otro"
                    if any(p in msg_lower for p in ["casa", "quinta", "chalet", "duplex"]):
                        tipo_detectado = "Casa"
                    elif any(p in msg_lower for p in ["apartamento", "apto", "depto", "ph", "flat"]):
                        tipo_detectado = "Apartamento"
                    elif any(p in msg_lower for p in ["local", "oficina", "consultorio", "comercial"]):
                        tipo_detectado = "Local/Oficina"
                    elif any(p in msg_lower for p in ["terreno", "finca", "lote", "parcela"]):
                        tipo_detectado = "Terreno"
                    elif any(p in msg_lower for p in ["galpon", "galp¨®n", "bodega", "almac¨¦n"]):
                        tipo_detectado = "Galp¨®n"

                    if tipo_inmueble and tipo_detectado != tipo_inmueble:
                        continue

                    telefono_match = re.search(r"(\+?\d{2,4}[\s-]?\d{3,4}[\s-]?\d{4,7})", mensaje)
                    telefono = telefono_match.group(1) if telefono_match else "No especificado"

                    requerimientos_lista.append({
                        "fecha": fecha_str,
                        "requerimiento": mensaje,
                        "contacto": contacto,
                        "telefono": telefono,
                        "tipo_inmueble": tipo_detectado
                    })
                    inmuebles_conteo.append(tipo_detectado)
                    agentes_lista.append(contacto)

    return {
        "tabla": requerimientos_lista,
        "estadisticas": dict(Counter(inmuebles_conteo)),
        "ranking": [{"nombre": k, "mensajes": v} for k, v in Counter(agentes_lista).most_common(5)]
    }

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    try:
        if 'file' not in request.files:
            return jsonify({"error": "No se subi¨® ning¨²n archivo"}), 400
        file = request.files['file']
        if file.filename == '':
            return jsonify({"error": "Archivo vac¨ªo"}), 400
            
        texto_chat = file.read().decode('utf-8', errors='ignore')
        f_inicio_str = request.form.get('fecha_inicio')
        f_fin_str = request.form.get('fecha_fin')
        tipo = request.form.get('tipo_inmueble') or None

        f_inicio = datetime.strptime(f_inicio_str, '%Y-%m-%d') if f_inicio_str else None
        f_fin = datetime.strptime(f_fin_str, '%Y-%m-%d').replace(hour=23, minute=59, second=59) if f_fin_str else None

        resultados = procesar_chat(texto_chat, f_inicio, f_fin, tipo)
        session['tabla_datos'] = resultados.get('tabla', [])

        response = jsonify(resultados)
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate'
        return response
    except Exception as e:
        print(f"? ERROR EN /upload: {traceback.format_exc()}")
        return jsonify({"error": "Error interno al procesar"}), 500

@app.route('/export/excel')
def export_excel():
    try:
        import pandas as pd
        from io import BytesIO
        data = session.get('tabla_datos', [])
        if not data:
            return jsonify({"error": "Sin datos para exportar"}), 404
        df = pd.DataFrame(data)
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Requerimientos')
        output.seek(0)
        return send_file(
            output,
            download_name='requerimientos_mobilia.xlsx',
            as_attachment=True,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    except Exception as e:
        print(f"? ERROR EN /export/excel: {traceback.format_exc()}")
        return jsonify({"error": "Error al generar Excel"}), 500

@app.route('/export/pdf')
def export_pdf():
    try:
        from weasyprint import HTML
        from io import BytesIO
        data = session.get('tabla_datos', [])
        if not data:
            return jsonify({"error": "Sin datos para exportar"}), 404
        
        html_content = """
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body { font-family: Arial, sans-serif; font-size: 12px; }
                h2 { color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px; }
                table { width: 100%; border-collapse: collapse; margin-top: 20px; }
                th { background-color: #3498db; color: white; padding: 10px; text-align: left; }
                td { padding: 8px; border-bottom: 1px solid #ddd; }
                tr:nth-child(even) { background-color: #f9f9f9; }
                .phone { color: #27ae60; font-weight: bold; }
            </style>
        </head>
        <body>
            <h2>?? Reporte Mobilia - Requerimientos</h2>
            <p><strong>Generado:</strong> """ + datetime.now().strftime("%d/%m/%Y %H:%M") + """</p>
            <table>
                <thead>
                    <tr>
                        <th>Fecha</th>
                        <th>Tipo</th>
                        <th>Requerimiento</th>
                        <th>Contacto</th>
                        <th>Tel¨¦fono</th>
                    </tr>
                </thead>
                <tbody>
        """
        for row in data:
            phone_display = f'<span class="phone">?? {row["telefono"]}</span>' if row["telefono"] != "No especificado" else "-"
            html_content += f"""
                    <tr>
                        <td>{row['fecha']}</td>
                        <td>{row['tipo_inmueble']}</td>
                        <td>{row['requerimiento']}</td>
                        <td>{row['contacto']}</td>
                        <td>{phone_display}</td>
                    </tr>
            """
        html_content += """
                </tbody>
            </table>
        </body>
        </html>
        """
        pdf_file = BytesIO()
        HTML(string=html_content).write_pdf(pdf_file)
        pdf_file.seek(0)
        return send_file(
            pdf_file,
            download_name='requerimientos_mobilia.pdf',
            as_attachment=True,
            mimetype='application/pdf'
        )
    except Exception as e:
        print(f"? ERROR EN /export/pdf: {traceback.format_exc()}")
        return jsonify({"error": "Error al generar PDF"}), 500

# Desactivar apertura autom¨¢tica de navegador en producci¨®n
def abrir_navegador():
    if os.getenv("FLASK_ENV") != "production":
        webbrowser.open("http://127.0.0.1:5000")

if __name__ == '__main__':
    if os.getenv("FLASK_ENV") != "production":
        Timer(1.5, abrir_navegador).start()
    app.run(debug=False, host='0.0.0.0', port=int(os.getenv("PORT", 5000)))