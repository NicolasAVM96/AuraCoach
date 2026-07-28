import re
from datetime import datetime

def parse_exercise(linea_texto):
    # Busca texto, luego numeros separados por 'x', luego el resto.
    # El [xX]? antes del resto es porque el formato habitual es
    # "RepsxSeriesxCarga" (tres campos separados por 'x', sin espacios) -
    # sin este optional, esa tercera 'x' quedaba pegada al inicio de la carga.
    patron_regex = r"^(.+?)\s+(\d+)[xX](\d+)[xX]?\s*(.*)$"

    # Intentamos hacer match con la linea que recibimos
    match = re.match(patron_regex, linea_texto)

    if match:
        ejercicio = match.group(1).strip()
        reps = int(match.group(2))
        series = int(match.group(3))
        carga = match.group(4).strip()
        
        # Devolvemos un diccionario limpio
        return {
            "fecha": datetime.now().strftime("%d/%m/%Y"),
            "tipo_entreno": None,
            "ejercicio": ejercicio,
            "series": series,
            "reps": reps,
            "carga": carga
        }
    else:
        return None



def procesar_mensaje_completo(mensaje_texto):
    # Separamos el mensaje en lineas
    lineas = mensaje_texto.strip().split('\n')
    
    # La primera línea es nuestra llave dinámica
    tipo_entreno = lineas[0].strip() 
    
    lista_ejercicios_listos = []
    
    # Iteramos desde la segunda línea hasta el final
    for linea in lineas[1:]:
        if linea.strip() == "":
            continue
            
        # Usamos Regex
        datos_ejercicio = parse_exercise(linea) 
        
        if datos_ejercicio:
            datos_ejercicio["tipo_entreno"] = tipo_entreno 
            lista_ejercicios_listos.append(datos_ejercicio)
        else:
            print(f"No pude entender esta linea: {linea}")
            
    return lista_ejercicios_listos



# --- Testing ---
# mensaje_prueba = """Gym Superior
# Tricep poleas 12x3 30lb
# Bicep supino 12x3 15kg
# Bicep martillo 12x3 10kg"""

# resultado = procesar_mensaje_completo(mensaje_prueba)
# if resultado:
#     for r in resultado:
#         print(r)
# else:
#     print(f"❌ Falló al leer: {resultado}")