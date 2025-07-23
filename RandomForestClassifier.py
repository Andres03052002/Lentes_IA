import pandas as pd
import mysql.connector
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import LabelEncoder
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.metrics import classification_report, confusion_matrix, ConfusionMatrixDisplay
from joblib import dump
import json
import logging
from datetime import datetime
import matplotlib.pyplot as plt
import seaborn as sns

# 📦 Logging
logging.basicConfig(
    filename='modelo_categoria.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logging.info("🚀 Iniciando entrenamiento por categoría...")

# 📦 Conexión DB
conn = mysql.connector.connect(
    host="AndresL12.mysql.pythonanywhere-services.com",
    user="AndresL12",
    password="0151021102andy",
    database="AndresL12$gafas_inteligentes"
)
cursor = conn.cursor()

# 📦 Cargar datos
df = pd.read_sql("""
    SELECT 
        u.genero, 
        u.actividad, 
        u.tipo_rostro,
        r.afinidad,
        l.categoria_lente
    FROM recomendaciones r
    JOIN usuarios u ON r.id_usuario = u.id_usuario
    JOIN lentes l ON r.id_lente = l.id_lente
    WHERE l.categoria_lente IS NOT NULL
""", conn)

if df.empty or len(df) < 10:
    print("❌ Datos insuficientes para entrenar.")
    logging.warning("❌ Datos insuficientes para entrenar.")
    exit(1)

# 📦 Codificación
le_genero = LabelEncoder()
le_actividad = LabelEncoder()
le_rostro = LabelEncoder()
le_categoria = LabelEncoder()

df['genero'] = le_genero.fit_transform(df['genero'])
df['actividad'] = le_actividad.fit_transform(df['actividad'])
df['tipo_rostro'] = le_rostro.fit_transform(df['tipo_rostro'])
df['categoria_lente'] = le_categoria.fit_transform(df['categoria_lente'])

X = df[['genero', 'actividad', 'tipo_rostro', 'afinidad']]
y = df['categoria_lente']

# 📦 Entrenamiento
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
modelo = RandomForestClassifier(n_estimators=100, random_state=42)
modelo.fit(X_train, y_train)

# 📦 Validación cruzada
cv_scores = cross_val_score(modelo, X, y, cv=5)
cv_accuracy = cv_scores.mean()
logging.info(f"📊 Cross-Validation Accuracy: {cv_accuracy:.4f}")

# 📦 Evaluación
y_pred = modelo.predict(X_test)
report = classification_report(y_test, y_pred, output_dict=True, zero_division=0)
cm = confusion_matrix(y_test, y_pred)

# 📦 Guardar métricas
metrics = {
    'accuracy': report['accuracy'],
    'precision': report['weighted avg']['precision'],
    'recall': report['weighted avg']['recall'],
    'f1': report['weighted avg']['f1-score'],
    'confusion_matrix': {
        'matrix': cm.tolist(),
        'labels': le_categoria.classes_.tolist()
    },
    'feature_importances': {
        'features': ['genero', 'actividad', 'tipo_rostro', 'afinidad'],
        'importances': modelo.feature_importances_.tolist()
    },
    'cross_val_accuracy': cv_accuracy,
    'last_trained': datetime.now().isoformat()
}
with open('model_categoria_metrics.json', 'w') as f:
    json.dump(metrics, f)
logging.info("📊 Métricas guardadas.")

# 📦 Guardar modelo y encoders
dump(modelo, 'modelo_categoria.joblib')
dump((le_genero, le_actividad, le_rostro, le_categoria), 'label_encoders_categoria.joblib')
logging.info("💾 Modelo de categoría y encoders guardados.")

# 📊 Visualización
plt.figure(figsize=(6, 4))
ConfusionMatrixDisplay.from_predictions(y_test, y_pred)
plt.title("Matriz de Confusión (Categorías)")
plt.show()

plt.figure(figsize=(6, 4))
sns.barplot(x=modelo.feature_importances_, y=['genero', 'actividad', 'tipo_rostro', 'afinidad'])
plt.title("Importancia de Características")
plt.show()

print("✅ Modelo de categorías entrenado con éxito.")
logging.info("✅ Entrenamiento por categoría finalizado.")
