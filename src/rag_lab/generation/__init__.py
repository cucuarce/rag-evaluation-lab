"""Etapa 2: generación de respuestas con citas y abstención.

Este paquete recibe solo la pregunta y los fragmentos recuperados. Nunca importa
`rag_lab.evaluation` ni lee etiquetas (verificado en tests/test_gen_leakage.py).
La calibración del umbral del gate usa etiquetas del split calibration y por eso vive en
`rag_lab.evaluation.gate_calibration`, fuera de este paquete.
"""
