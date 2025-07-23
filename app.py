from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit
import threading
import cv2, base64, numpy as np, mediapipe as mp
import pymysql
from pymysql.err import MySQLError
from joblib import load
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv
import os, json, time
from flask import Flask, render_template, request, redirect, url_for, session

# Cargar configuración
load_dotenv()
dbconfig = {
    "host": os.getenv("DB_HOST", "AndresL12.mysql.pythonanywhere-services.com"),
    "user": os.getenv("DB_USER", "AndresL12"),
    "password": os.getenv("DB_PASSWORD", "0151021102andy"),
    "database": os.getenv("DB_NAME", "AndresL12$gafas_inteligentes"),
    "cursorclass": pymysql.cursors.DictCursor,
    "autocommit": True
}

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

app.secret_key = '123' 

# Cargar modelo y encoders
try:
    modelo = load("modelo_categoria.joblib")
    le_genero, le_actividad, le_rostro, le_categoria = load("label_encoders_categoria.joblib")
    print("✅ Modelo y encoders cargados")
except FileNotFoundError:
    modelo, le_genero, le_actividad, le_rostro = None, None, None, None
    print("⚠️ Modelo no encontrado. Ejecuta RandomForestClassifier.py")

# Funciones auxiliares
def get_connection():
    try:
        return pymysql.connect(**dbconfig)
    except MySQLError as e:
        print(f"❌ Error de conexión MySQL: {e}")
        return None

def guardar_usuario(genero, actividad, tipo_rostro):
    conn = get_connection()
    if not conn:
        return None
    try:
        with conn.cursor() as cursor:
            sql = """
                INSERT INTO usuarios (genero, actividad, tipo_rostro)
                VALUES (%s, %s, %s)
            """
            cursor.execute(sql, (genero, actividad, tipo_rostro))
            conn.commit()
            return cursor.lastrowid
    except MySQLError as e:
        print(f"❌ Error guardando usuario: {e}")
        return None
    finally:
        conn.close()

# Rutas

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        # 🛡️ Validación de credenciales (aquí puedes conectar con tu DB)
        if username == 'admin' and password == '1234':
            session['is_admin'] = True
            return redirect(url_for('admin_dashboard'))
        else:
            return "❌ Usuario o contraseña incorrectos", 401
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('inicio'))

@app.route('/')
def inicio():
    return render_template('index.html')

@app.route('/recomendador')
def recomendador():
    return render_template('recomendador.html')

@app.route('/test-daltonismo')
def test_daltonismo():
    return render_template('test-daltonismo.html')

@app.route('/admin')
def admin_dashboard():
    if not session.get('is_admin'):
        return redirect(url_for('login'))  # Redirige a login si no es admin
    try:
        with open('model_metrics.json', 'r') as f:
            metrics = json.load(f)
    except:
        metrics = {"accuracy": 0, "precision": 0, "recall": 0, "f1": 0,
                   "confusion_matrix": {"matrix": [[0]], "labels": ["N/A"]},
                   "feature_importances": {"features": [], "importances": []}}
    return render_template('admin_dashboard.html', metrics=metrics)

@app.route('/api/recomendar', methods=['POST'])
def recomendar():
    try:
        data = request.get_json()
        print("📦 Datos /api/recomendar:", data)
        print("🔍 Modelo cargado:", modelo is not None)
        print("🔍 Encoders cargados:", le_genero is not None)
        
        if modelo is None or le_genero is None:
            print("❌ Modelo o encoders no cargados")
            return jsonify({"error": "Modelo no cargado"}), 500

        print("💾 Guardando usuario...")
        id_usuario = guardar_usuario(data['genero'], data['actividad'], data['tipo_rostro'])
        print("💾 ID usuario:", id_usuario)
        if not id_usuario:
            print("❌ Error guardando usuario")
            return jsonify({"error": "Error guardando usuario"}), 500

        x_input = pd.DataFrame([{
            "genero": le_genero.transform([data['genero']])[0],
            "actividad": le_actividad.transform([data['actividad']])[0],
            "tipo_rostro": le_rostro.transform([data['tipo_rostro']])[0],
            "afinidad": 80  # valor promedio inicial si no se tiene feedback previo
        }])

        # 🔮 Predicción de categoría
        proba = modelo.predict_proba(x_input)[0]
        categorias_ordenadas = modelo.classes_[proba.argsort()[::-1][:2]]
        recomendaciones = []

        print("🔌 Conectando a la base de datos...")
        conn = get_connection()
        if not conn:
            print("❌ Error de conexión a la base de datos")
            return jsonify({"error": "Error de conexión a la base de datos"}), 500
        print("✅ Conexión exitosa")

        try:
            with conn.cursor() as cursor:
                for cat_encoded in categorias_ordenadas:
                    categoria = le_categoria.inverse_transform([cat_encoded])[0]
                    cursor.execute("""
                        SELECT * FROM lentes
                        WHERE categoria_lente = %s
                        ORDER BY RAND()
                        LIMIT 2
                    """, (categoria,))
                    lentes = cursor.fetchall()
                    for lente in lentes:
                        afinidad = int(proba[list(modelo.classes_).index(cat_encoded)] * 100)
                        cursor.execute("""
                            INSERT INTO recomendaciones (id_usuario, id_lente, afinidad)
                            VALUES (%s, %s, %s)
                        """, (id_usuario, lente['id_lente'], afinidad))
                        recomendaciones.append({
                            "id_lente": lente['id_lente'],
                            "modelo": lente['sku'],
                            "nombre": lente['nombre'],
                            "img": lente['imagen_url'] or "/static/img/lente_default.jpg",
                            "precio": str(lente['precio']) or "N/A",
                            "afinidad": afinidad
                        })
        finally:
            conn.close()

        return jsonify({"recomendaciones": recomendaciones, "id_usuario": id_usuario})
    except Exception as e:
        print(f"❌ Error /api/recomendar: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/feedback', methods=['POST'])
def feedback():
    try:
        data = request.get_json()
        conn = get_connection()
        if not conn:
            return jsonify({"error": "Error de conexión a la base de datos"}), 500
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO logs_uso (id_usuario, id_lente, afinidad, accion, feedback_like, fecha_log)
                    VALUES (%s, %s, %s, %s, %s, NOW())
                """, (
                    int(data['id_usuario']),
                    int(data['id_lente']),
                    int(data.get('afinidad', 0)),
                    data['accion'],
                    int(data['like']) if data.get('like') is not None else None
                ))
                socketio.emit('update_dashboard', {'message': 'Nuevo feedback'})
        finally:
            conn.close()
        return jsonify({"success": True})
    except Exception as e:
        print(f"❌ Error /api/feedback: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/model-metrics', methods=['GET'])
def model_metrics():
    try:
        print("📂 Abriendo model_metrics.json...")
        with open('model_categoria_metrics.json', 'r') as f:
            metrics = json.load(f)
        print("✅ JSON cargado:", metrics)

        conn = get_connection()
        if not conn:
            print("❌ Falló conexión a la base de datos")
            return jsonify(metrics)

        try:
            with conn.cursor() as cursor:
                # Likes y dislikes usando feedback_like
                cursor.execute("SELECT COUNT(*) AS likes FROM logs_uso WHERE feedback_like=1")
                likes = cursor.fetchone()['likes'] or 0

                cursor.execute("SELECT COUNT(*) AS dislikes FROM logs_uso WHERE feedback_like=0")
                dislikes = cursor.fetchone()['dislikes'] or 0

                # Intenciones de compra usando accion='intencion_compra'
                cursor.execute("SELECT COUNT(*) AS compras FROM logs_uso WHERE accion='comprar'")
                compras = cursor.fetchone()['compras'] or 0

                # Distribución de usuarios por género
                cursor.execute("SELECT genero, COUNT(*) AS total FROM usuarios GROUP BY genero")
                genero_data = cursor.fetchall()

                # Distribución de usuarios por tipo de rostro
                cursor.execute("SELECT tipo_rostro, COUNT(*) AS total FROM usuarios GROUP BY tipo_rostro")
                rostro_data = cursor.fetchall()

                # Acciones de los usuarios
                cursor.execute("SELECT accion, COUNT(*) AS total FROM logs_uso GROUP BY accion")
                acciones_data = cursor.fetchall()

                # Tasa de conversión (intenciones de compra / recomendaciones)
                cursor.execute("SELECT COUNT(*) AS total_recomendaciones FROM recomendaciones")
                total_recomendaciones = cursor.fetchone()['total_recomendaciones'] or 0

                cursor.execute("SELECT COUNT(*) AS total_intenciones FROM logs_uso WHERE accion='compra'")
                total_intenciones = cursor.fetchone()['total_intenciones'] or 0

                conversion_rate = (total_intenciones / total_recomendaciones * 100) if total_recomendaciones else 0

                # Top 5 modelos más con intención de compra
                cursor.execute("""
                    SELECT l.nombre, COUNT(*) AS total
                    FROM logs_uso lu
                    JOIN lentes l ON lu.id_lente = l.id_lente
                    WHERE lu.accion='comprar'
                    GROUP BY l.nombre
                    ORDER BY total DESC
                    LIMIT 5
                """)
                top_compras = cursor.fetchall()

                # Actualizar el diccionario de métricas
                metrics.update({
                    "total_likes": likes,
                    "total_dislikes": dislikes,
                    "total_compras": compras,
                    "genero_data": genero_data,
                    "rostro_data": rostro_data,
                    "acciones_data": acciones_data,
                    "conversion_rate": conversion_rate,
                    "top_compras": top_compras
                })
                print("✅ Métricas actualizadas:", metrics)
        finally:
            conn.close()

        return jsonify(metrics)
    except Exception as e:
        print(f"❌ Error /api/model-metrics: {e}")
        return jsonify({"error": str(e)}), 500

import subprocess

@app.route('/api/reentrenar', methods=['POST'])
def reentrenar():
    try:
        result = subprocess.run(['python', 'RandomForestClassifier.py'], capture_output=True, text=True, timeout=60)
        if result.returncode == 0:
            return jsonify({"success": True, "output": result.stdout})
        else:
            print(f"❌ Error al reentrenar:\n{result.stderr}")
            return jsonify({"error": result.stderr}), 500
    except Exception as e:
        print(f"❌ Excepción en reentrenamiento: {e}")
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5001, debug=False)
