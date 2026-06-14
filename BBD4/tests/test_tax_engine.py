"""
test_tax_engine.py — Tests unitarios del motor fiscal FIFO / LIFO.
Son tests PURAMENTE unitarios (sin DB ni HTTP), deben ser 100% deterministas.
"""
import pytest
from datetime import datetime, timedelta
from services.tax_engine import (calcular_ganancias_capital, generar_lotes_desde_ordenes,
                                  calcular_tax_report_anual)


def _lot(ticker, acc, costo, dias_atras=0):
    return {
        "ticker": ticker,
        "acciones_restantes": acc,
        "precio_costo": costo,
        "fecha_compra": datetime.utcnow() - timedelta(days=dias_atras)
    }

def _venta(ticker, acc, precio, dias_atras=0):
    return {
        "ticker": ticker,
        "acciones": acc,
        "precio_venta": precio,
        "fecha_venta": datetime.utcnow() - timedelta(days=dias_atras)
    }


class TestFIFO:
    def test_ganancia_simple(self):
        lots = [_lot("AAPL", 10, 100.0, dias_atras=400)]
        ventas = [_venta("AAPL", 5, 150.0)]
        r = calcular_ganancias_capital(lots, ventas, metodo="FIFO")
        assert r["total_ganancias"] == pytest.approx(250.0)  # (150-100)*5
        assert r["total_perdidas"] == 0.0
        assert r["ganancia_neta"] == pytest.approx(250.0)

    def test_perdida_simple(self):
        lots = [_lot("TSLA", 2, 300.0, dias_atras=10)]
        ventas = [_venta("TSLA", 2, 200.0)]
        r = calcular_ganancias_capital(lots, ventas, metodo="FIFO")
        assert r["total_perdidas"] == pytest.approx(200.0)  # (300-200)*2
        assert r["ganancia_neta"] == pytest.approx(-200.0)

    def test_fifo_multiples_lotes(self):
        """Con 2 lotes, FIFO consume primero el más antiguo."""
        lots = [
            _lot("MSFT", 5, 100.0, dias_atras=500),   # lote antiguo, costo 100
            _lot("MSFT", 5, 200.0, dias_atras=100),   # lote nuevo, costo 200
        ]
        ventas = [_venta("MSFT", 5, 250.0)]
        r = calcular_ganancias_capital(lots, ventas, metodo="FIFO")
        # FIFO: usa lote antiguo (costo 100) → ganancia = (250-100)*5 = 750
        assert r["total_ganancias"] == pytest.approx(750.0)

    def test_largo_plazo_vs_corto_plazo(self):
        """Lotes con >365 días deben clasificarse como largo plazo."""
        lots = [
            _lot("SPY", 10, 100.0, dias_atras=400),  # largo plazo
        ]
        ventas = [_venta("SPY", 10, 120.0)]
        r = calcular_ganancias_capital(lots, ventas, metodo="FIFO",
                                       tax_rate_st=0.30, tax_rate_lt=0.20)
        assert r["ganancias_largo_plazo"] == pytest.approx(200.0)  # (120-100)*10
        assert r["ganancias_corto_plazo"] == 0.0
        # Impuesto: 200 * 20% = 40
        assert r["impuesto_estimado"] == pytest.approx(40.0)

    def test_corto_plazo_impuesto(self):
        lots = [_lot("NVDA", 3, 500.0, dias_atras=100)]  # corto plazo
        ventas = [_venta("NVDA", 3, 600.0)]
        r = calcular_ganancias_capital(lots, ventas, metodo="FIFO",
                                       tax_rate_st=0.30, tax_rate_lt=0.20)
        # ganancia = (600-500)*3 = 300, corto plazo
        assert r["ganancias_corto_plazo"] == pytest.approx(300.0)
        assert r["impuesto_estimado"] == pytest.approx(90.0)  # 300*0.30

    def test_sin_lotes_suficientes(self):
        """Si no hay lotes suficientes, el engine no falla."""
        lots = [_lot("AMZN", 1, 150.0, dias_atras=50)]
        ventas = [_venta("AMZN", 5, 200.0)]  # vende más de lo que tiene
        r = calcular_ganancias_capital(lots, ventas, metodo="FIFO")
        assert "total_ganancias" in r  # no lanza excepción


class TestLIFO:
    def test_lifo_usa_lote_mas_reciente(self):
        """Con 2 lotes, LIFO consume primero el más reciente."""
        lots = [
            _lot("AAPL", 5, 100.0, dias_atras=500),  # antiguo
            _lot("AAPL", 5, 200.0, dias_atras=10),   # reciente, costo 200
        ]
        ventas = [_venta("AAPL", 5, 250.0)]
        r = calcular_ganancias_capital(lots, ventas, metodo="LIFO")
        # LIFO: usa lote reciente (costo 200) → ganancia = (250-200)*5 = 250
        assert r["total_ganancias"] == pytest.approx(250.0)


class TestGenLotesDesdeOrdenes:
    def test_genera_lotes_de_compras(self):
        ordenes = [
            {"tipo": "buy", "estado": "filled", "ticker": "AAPL",
             "acciones": 2.0, "precio_ejecucion": 180.0,
             "ejecutado": datetime.utcnow().isoformat(), "id": 1},
            {"tipo": "sell", "estado": "filled", "ticker": "AAPL",
             "acciones": 1.0, "precio_ejecucion": 200.0,
             "ejecutado": datetime.utcnow().isoformat(), "id": 2},
        ]
        lotes = generar_lotes_desde_ordenes(ordenes)
        assert len(lotes) == 1  # solo la compra
        assert lotes[0]["ticker"] == "AAPL"
        assert lotes[0]["acciones_restantes"] == 2.0

    def test_ignora_ordenes_canceladas(self):
        ordenes = [
            {"tipo": "buy", "estado": "cancelled", "ticker": "MSFT",
             "acciones": 5.0, "precio_ejecucion": 400.0,
             "ejecutado": None, "id": 3},
        ]
        lotes = generar_lotes_desde_ordenes(ordenes)
        assert len(lotes) == 0


class TestReporteAnual:
    def test_reporte_anual_sin_ventas(self):
        ordenes = [
            {"tipo": "buy", "estado": "filled", "ticker": "SPY",
             "acciones": 5.0, "precio_ejecucion": 500.0,
             "ejecutado": "2024-06-01T00:00:00", "creado": "2024-06-01T00:00:00", "id": 10}
        ]
        r = calcular_tax_report_anual(ordenes, 2024)
        assert r["total_ganancias"] == 0.0
        assert r["impuesto_estimado"] == 0.0

    def test_reporte_anual_con_ventas(self):
        ordenes = [
            {"tipo": "buy", "estado": "filled", "ticker": "SPY",
             "acciones": 5.0, "precio_ejecucion": 400.0,
             "ejecutado": "2022-01-01T00:00:00", "creado": "2022-01-01T00:00:00", "id": 11},
            {"tipo": "sell", "estado": "filled", "ticker": "SPY",
             "acciones": 3.0, "precio_ejecucion": 500.0,
             "ejecutado": "2024-06-01T00:00:00", "creado": "2024-06-01T00:00:00", "id": 12},
        ]
        r = calcular_tax_report_anual(ordenes, 2024)
        # ganancia = (500-400)*3 = 300, largo plazo (>365 días)
        assert r["total_ganancias"] == pytest.approx(300.0)
        assert r["ganancias_largo_plazo"] == pytest.approx(300.0)
