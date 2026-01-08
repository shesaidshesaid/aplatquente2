import base64
from pathlib import Path

html_content = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AgroVale - Produtos Agropecuários e Veterinários</title>
    <style>
        * {{

            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #2d5016 0%, #6ba839 100%);
            color: #333;
            line-height: 1.6;
        }}
        header {{
            background: linear-gradient(135deg, #1a3a0a 0%, #2d5016 100%);
            color: white;
            padding: 40px 20px;
            text-align: center;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }}
        header h1 {{
            font-size: 3em;
            margin-bottom: 10px;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
        }}
        header p {{
            font-size: 1.2em;
            opacity: 0.9;
        }}
        .info-proprietario {{
            background: rgba(255,255,255,0.1);
            padding: 15px;
            margin-top: 20px;
            border-radius: 8px;
            font-size: 0.95em;
        }}
        .container {{
            max-width: 1200px;
            margin: 40px auto;
            padding: 0 20px;
        }}
        .produtos {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
            gap: 30px;
            margin-bottom: 40px;
        }}
        .produto {{
            background: white;
            border-radius: 12px;
            overflow: hidden;
            box-shadow: 0 8px 16px rgba(0,0,0,0.15);
            transition: transform 0.3s ease, box-shadow 0.3s ease;
        }}
        .produto:hover {{
            transform: translateY(-10px);
            box-shadow: 0 12px 24px rgba(0,0,0,0.2);
        }}
        .produto-imagem {{
            width: 100%;
            height: 350px;
            background: linear-gradient(135deg, #90ee90, #228b22);
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 5em;
            overflow: hidden;
        }}
        .produto-info {{
            padding: 20px;
        }}
        .produto-info h3 {{
            color: #1a3a0a;
            margin-bottom: 10px;
            font-size: 1.3em;
        }}
        .categoria {{
            display: inline-block;
            background: #6ba839;
            color: white;
            padding: 5px 10px;
            border-radius: 4px;
            font-size: 0.75em;
            margin-bottom: 10px;
            font-weight: bold;
        }}
        .produto-info p {{
            color: #666;
            font-size: 0.95em;
            margin-bottom: 15px;
        }}
        .produto-preco {{
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .preco {{
            font-size: 1.8em;
            color: #2d5016;
            font-weight: bold;
        }}
        .btn {{
            background: linear-gradient(135deg, #6ba839, #4a7c2c);
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 6px;
            cursor: pointer;
            font-weight: bold;
            transition: background 0.3s ease;
        }}
        .btn:hover {{
            background: linear-gradient(135deg, #5a9e2e, #3a6c1c);
        }}
        footer {{
            background: #1a3a0a;
            color: white;
            text-align: center;
            padding: 30px 20px;
            margin-top: 50px;
        }}
        footer p {{
            margin-bottom: 10px;
        }}
        .contato {{
            margin-top: 20px;
            font-size: 0.95em;
        }}
    </style>
</head>
<body>
    <header>
        <h1>🌾 AgroVale Teresópolis 🌾</h1>
        <p>Produtos Agropecuários e Veterinários de Qualidade</p>
        <div class="info-proprietario">
            <strong>Proprietário:</strong> Luiz Gustavo<br>
            <strong>Localização:</strong> Teresópolis - RJ
        </div>
    </header>

    <div class="container">
        <div class="produtos">
            {produtos_html}
        </div>
    </div>

    <footer>
        <p><strong>AgroVale Teresópolis - Excelência em Produtos Agropecuários e Veterinários</strong></p>
        <div class="contato">
            <p><strong>Proprietário:</strong> Luiz Gustavo</p>
            <p>📞 Telefone: (24) 99999-8888</p>
            <p>📧 Email: luizgustavo@agrovale.com.br</p>
            <p>📍 Endereço: Teresópolis - RJ</p>
        </div>
        <p style="margin-top: 20px; opacity: 0.8;">&copy; 2024 AgroVale Teresópolis. Todos os direitos reservados.</p>
    </footer>
</body>
</html>
"""

# Lista de produtos com emojis genéricos (sem precisar baixar imagens)
produtos = [
    {"emoji": "🌽", "nome": "Milho Premium", "categoria": "Alimentação", "descricao": "Milho de alta qualidade para ração animal.", "preco": "4.50"},
    {"emoji": "💊", "nome": "Vermífugo Veterinário", "categoria": "Veterinário", "descricao": "Vermífugo eficaz para bovinos e equinos.", "preco": "45.00"},
    {"emoji": "💉", "nome": "Vacina Antirrábica", "categoria": "Veterinário", "descricao": "Vacina para proteção contra raiva em animais.", "preco": "65.00"},
    {"emoji": "🐄", "nome": "Ração Bovina Premium", "categoria": "Alimentação", "descricao": "Ração balanceada com minerais e vitaminas.", "preco": "55.00"},
    {"emoji": "🧪", "nome": "Antibiótico Veterinário", "categoria": "Veterinário", "descricao": "Antibiótico de amplo espectro para animais.", "preco": "78.50"},
    {"emoji": "🥕", "nome": "Cenoura Fresca", "categoria": "Alimentação", "descricao": "Cenoura orgânica para animais e consumo.", "preco": "2.50"},
    {"emoji": "🧴", "nome": "Shampoo Veterinário", "categoria": "Cuidados", "descricao": "Shampoo antiparasitário para cães e gatos.", "preco": "35.00"},
    {"emoji": "🌾", "nome": "Sementes de Soja", "categoria": "Alimentação", "descricao": "Sementes certificadas para plantio.", "preco": "8.90"},
]

# Gerar HTML dos produtos dinamicamente
produtos_html = ""
for produto in produtos:
    produtos_html += f"""
            <div class="produto">
                <div class="produto-imagem">
                    {produto['emoji']}
                </div>
                <div class="produto-info">
                    <span class="categoria">{produto['categoria']}</span>
                    <h3>{produto['nome']}</h3>
                    <p>{produto['descricao']}</p>
                    <div class="produto-preco">
                        <span class="preco">R$ {produto['preco']}</span>
                        <button class="btn">Comprar</button>
                    </div>
                </div>
            </div>
"""

# Inserir produtos no template
html_final = html_content.format(produtos_html=produtos_html)

# Salvar arquivo HTML
with open("agrovale_teresopolis.html", "w", encoding="utf-8") as arquivo:
    arquivo.write(html_final)

print("✅ Página HTML gerada com sucesso: agrovale_teresopolis.html")
print("📌 Abra o arquivo no navegador para visualizar")
