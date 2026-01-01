# aplatquente/aplatquente.py
import sys
import argparse
from datetime import datetime

from aplatquente.infra import (
    create_edge_driver,
    attempt_auto_login,
    prompt_manual_login,
    perform_search,
    clicar_botao_confirmar_rodape,
    fechar_modal_etapa,
)

from aplatquente.plano import (
    gerar_plano_trabalho_quente,
    imprimir_plano,
    aplicar_plano,
)


def parse_args():
    parser = argparse.ArgumentParser(description="Automação APLAT - Trabalho a Quente")

    parser.add_argument("--valor", "-v", nargs="+", required=True, help="Número(s) da etapa a processar")
    parser.add_argument("--data", "-d", required=True, help="Data YYYY-MM-DD. Ex: 2026-01-03")

    parser.add_argument("--use-keyring", action="store_true", help="Usar keyring (requer --user)")
    parser.add_argument("--user", help="Usuário do login (obrigatório se usar --use-keyring)")
    parser.add_argument("--keyring-service", default="aplat.petrobras", help="Serviço do keyring")

    parser.add_argument("--timeout", type=float, default=30.0, help="Timeout padrão (s)")
    parser.add_argument("--search-timeout", type=float, default=30.0, help="Timeout da busca (s)")

    parser.add_argument(
        "--url",
        default="https://aplat.petrobras.com.br/#/permissaotrabalho/P-18/planejamento/programacaodiaria",
        help="URL do APLAT",
    )
    return parser.parse_args()


def _convert_data_yyyy_mm_dd_to_dd_mm_yyyy(data_str: str) -> str:
    try:
        dt = datetime.strptime(data_str, "%Y-%m-%d")
        return dt.strftime("%d/%m/%Y")
    except ValueError:
        return data_str


def main():
    args = parse_args()

    if args.use_keyring and not args.user:
        print("[ERROR] Você usou --use-keyring, então também precisa informar --user.")
        return 2

    driver = create_edge_driver()

    try:
        data_ui = _convert_data_yyyy_mm_dd_to_dd_mm_yyyy(args.data)

        logged_in = attempt_auto_login(
            driver,
            args.url,
            args.timeout,
            use_keyring=args.use_keyring,
            user=args.user,
            keyring_service=args.keyring_service,
        )

        if not logged_in:
            prompt_manual_login(driver, args.timeout)

        for etapa in args.valor:
            # 1) Abrir etapa
            try:
                perform_search(driver, data_ui, etapa, args.timeout, args.search_timeout, detail_wait=0.3)
                print(f"[INFO] Etapa {etapa} aberta com sucesso.")
            except Exception as e:
                print(f"[ERROR] Falha ao buscar/abrir etapa {etapa}: {e}")
                continue

            # 2) Gerar plano
            try:
                plano = gerar_plano_trabalho_quente(driver, args.timeout)
                imprimir_plano(plano)
            except Exception as e:
                print(f"[ERROR] Falha ao gerar plano para {etapa}: {e}")
                # tenta fechar o modal para não travar o loop
                try:
                    fechar_modal_etapa(driver, args.timeout)
                except Exception:
                    pass
                continue

            # 3) Aplicar plano (preenchimentos + confirmar por aba, se você implementar assim)
            try:
                resultado = aplicar_plano(driver, plano, args.timeout)  # <-- ORDEM CORRETA
                print(f"[INFO] Preenchimento concluído: {resultado}")
            except Exception as e:
                print(f"[WARN] Preenchimento com erro em {etapa}: {e}")
                # continua mesmo assim para tentar fechar/seguir

            # 4) Confirmação final + fechar (mesmo que o aplicar_plano já confirme por aba)
            try:
                clicar_botao_confirmar_rodape(driver, args.timeout)
            except Exception as e:
                print(f"[WARN] Não foi possível confirmar no final da etapa {etapa}: {e}")

            try:
                fechar_modal_etapa(driver, args.timeout)
            except Exception as e:
                print(f"[WARN] Não foi possível fechar o modal da etapa {etapa}: {e}")

        input("Pressione ENTER para encerrar...")  # útil enquanto você está testando

    finally:
        try:
            driver.quit()
        except Exception:
            pass

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
