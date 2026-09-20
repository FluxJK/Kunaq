from typing import List
from src.modelos import Paciente, PersonalSalud, Medico, Enfermero

def ejecutar_prueba_viabilidad():
    print("==========================================================================")
    print("                SISTEMARURAL-PE  |  PRUEBA DE VIABILIDAD                  ")
    print("==========================================================================\n")

    # Instanciación de objetos Paciente
    p1 = Paciente("Juan Pérez Ruiz", "72849102", "Puesto de Salud Alto Trujillo")
    p2 = Paciente("María Gómez Lázaro", "41928374", "Caserío Conache")

    # Colección homogénea polimórfica (typing.List)
    equipo_salud: List[PersonalSalud] = [
        Medico("Carlos Mendoza", "18293041", "Medicina General - Hosp. Regional"),
        Enfermero("Ana Torres", "29384710", "Triaje y Vacunación")
    ]

    print("--- REGISTRO DE ATENCIONES MÉDICAS PROGRAMADAS ---\n")
    for profesional, paciente in zip(equipo_salud, [p1, p2]):
        print(profesional.atender(paciente))
        print() # Espacio en blanco entre atenciones

    print("--------------------------------------------------------------------------")
    print(" [VEREDICTO]: Prueba ejecutada correctamente en el intérprete de Python.")
    print("==========================================================================\n")

if __name__ == "__main__":
    ejecutar_prueba_viabilidad()