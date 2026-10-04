"""
Módulo de Interfaz Gráfica de Usuario (GUI) con Tkinter
Diseño ligero e intituitivo optimizado para PCs de bajos recursos en puestos de salud.
"""

import tkinter as tk
from tkinter import messagebox, ttk
from src.base_datos import BaseDatosLocal
from src.inventario import ControlInventario
from src.sincronizacion import GestorAlertasEmergencia


class VentanaPrincipalSistema:
    """Gestiona la interfaz gráfica del Puesto de Salud Rural."""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("SistemaRural-PE | Gestión de Salud Rural")
        self.root.geometry("600x500")

        self.db = BaseDatosLocal()
        self.inventario = ControlInventario()

        self._crear_componentes()

    def _crear_componentes(self):
        """Construye los elementos de la interfaz de usuario."""
        # Título principal
        lbl_titulo = tk.Label(
            self.root, 
            text="Sistema Rural de Salud - La Libertad", 
            font=("Arial", 14, "bold")
        )
        lbl_titulo.pack(pady=10)

        # Marco de Registro de Atención
        frame_registro = tk.LabelFrame(self.root, text=" Registrar Atención Médica ", padding=10)
        frame_registro.pack(fill="x", padx=15, pady=5)

        tk.Label(frame_registro, text="DNI Hash Paciente:").grid(row=0, column=0, sticky="w", pady=2)
        self.ent_dni = tk.Entry(frame_registro, width=30)
        self.ent_dni.grid(row=0, column=1, pady=2)

        tk.Label(frame_registro, text="Diagnóstico:").grid(row=1, column=0, sticky="w", pady=2)
        self.ent_diag = tk.Entry(frame_registro, width=30)
        self.ent_diag.grid(row=1, column=1, pady=2)

        btn_guardar = tk.Button(
            frame_registro, 
            text="Guardar Atención", 
            command=self._guardar_atencion, 
            bg="#28a745", 
            fg="white"
        )
        btn_guardar.grid(row=2, columnspan=2, pady=8)

        # Marco de Inventario de Medicamentos
        frame_inv = tk.LabelFrame(self.root, text=" Consulta de Stock de Medicamentos ", padding=10)
        frame_inv.pack(fill="both", expand=True, padx=15, pady=5)

        btn_cargar_inv = tk.Button(
            frame_inv, 
            text="Verificar Medicamentos Críticos", 
            command=self._mostrar_criticos
        )
        btn_cargar_inv.pack(anchor="w", pady=2)

        self.txt_inventario = tk.Text(frame_inv, height=8, width=65)
        self.txt_inventario.pack(fill="both", expand=True, pady=5)

    def _guardar_atencion(self):
        """Manejador para el botón de registro de atención."""
        dni = self.ent_dni.get().strip()
        diag = self.ent_diag.get().strip()

        if not dni or not diag:
            messagebox.showwarning("Advertencia", "Por favor complete todos los campos.")
            return

        exito = self.db.registrar_atencion(dni_hash=dni, medico="Dr. Guardia", diagnostico=diag)
        if exito:
            messagebox.showinfo("Éxito", "Atención registrada correctamente localmente.")
            self.ent_dni.delete(0, tk.END)
            self.ent_diag.delete(0, tk.END)
        else:
            messagebox.showerror("Error", "No se pudo guardar la atención.")

    def _mostrar_criticos(self):
        """Muestra los medicamentos con stock bajo en el área de texto."""
        criticos = self.inventario.obtener_medicamentos_criticos()
        self.txt_inventario.delete("1.0", tk.END)
        
        if not criticos:
            self.txt_inventario.insert(tk.END, "Todos los medicamentos cuentan con stock adecuado.\n")
            return

        self.txt_inventario.insert(tk.END, "⚠️️ ALERTA: Medicamentos con Stock Crítico:\n\n")
        for m in criticos:
            self.txt_inventario.insert(
                tk.END, 
                f"• {m['nombre']} | Quedan: {m['stock']} unidades (Mínimo: {m['stock_minimo']})\n"
            )


def iniciar_gui():
    """Función de entrada para arrancar la interfaz."""
    root = tk.Tk()
    app = VentanaPrincipalSistema(root)
    root.mainloop()