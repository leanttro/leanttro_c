<!DOCTYPE html>
<html lang="pt-br">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{% block title %}Cesta de Presentes{% endblock %} | cestadepresentes.com.br</title>
  <meta name="description" content="{% block description %}Cestas de presentes artesanais para todas as ocasiões. Café da manhã, Dia dos Namorados, aniversário e muito mais. Entrega em São Paulo.{% endblock %}">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,400;0,700;1,400&family=DM+Sans:wght@300;400;500&display=swap" rel="stylesheet">
  <script src="https://sdk.mercadopago.com/js/v2"></script>
  <style>
    :root {
      --cream: #fdf6ee;
      --warm: #f5e6d0;
      --red: #c0392b;
      --red-dark: #962d22;
      --gold: #c9a84c;
      --brown: #5a3e2b;
      --brown-light: #7a6152;
      --text: #2d1f14;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: 'DM Sans', sans-serif; background: var(--cream); color: var(--text); }
    h1,h2,h3 { font-family: 'Playfair Display', serif; }
    a { text-decoration: none; color: inherit; }
    
    /* NAV */
    nav {
      background: #fff;
      border-bottom: 1px solid var(--warm);
      padding: 0 24px;
      display: flex; align-items: center; justify-content: space-between;
      height: 64px;
      position: sticky; top: 0; z-index: 100;
      box-shadow: 0 2px 12px rgba(90,62,43,.06);
    }
    .nav-logo { display: flex; align-items: center; gap: 10px; }
    .nav-logo-icon {
      width: 36px; height: 36px; background: linear-gradient(135deg, var(--red), #e74c3c);
      border-radius: 10px; display: flex; align-items: center; justify-content: center;
      font-size: 18px;
    }
    .nav-logo-text { font-family: 'Playfair Display', serif; font-size: 18px; color: var(--brown); }
    .nav-links { display: flex; gap: 24px; }
    .nav-links a { font-size: 14px; color: var(--brown-light); font-weight: 500; transition: color .2s; }
    .nav-links a:hover { color: var(--red); }
    .nav-cart {
      background: var(--red); color: #fff; border: none; cursor: pointer;
      padding: 8px 18px; border-radius: 8px; font-size: 14px; font-weight: 500;
      display: flex; align-items: center; gap: 6px; transition: background .2s;
    }
    .nav-cart:hover { background: var(--red-dark); }

    /* FOOTER */
    footer {
      background: var(--brown); color: var(--warm);
      padding: 40px 24px; margin-top: 80px; text-align: center;
    }
    footer .footer-logo { font-family: 'Playfair Display', serif; font-size: 22px; color: #fff; margin-bottom: 8px; }
    footer p { font-size: 13px; opacity: .7; }
    footer a { color: var(--gold); }

    /* UTILS */
    .btn { display: inline-flex; align-items: center; justify-content: center; gap: 8px; padding: 14px 28px; border-radius: 10px; font-weight: 500; font-size: 15px; cursor: pointer; transition: all .2s; border: none; }
    .btn-primary { background: var(--red); color: #fff; }
    .btn-primary:hover { background: var(--red-dark); transform: translateY(-1px); box-shadow: 0 4px 16px rgba(192,57,43,.3); }
    .btn-outline { background: transparent; border: 2px solid var(--red); color: var(--red); }
    .btn-outline:hover { background: var(--red); color: #fff; }
    .badge { display: inline-block; padding: 3px 10px; border-radius: 20px; font-size: 11px; font-weight: 500; text-transform: uppercase; letter-spacing: .5px; }
    .badge-gold { background: #fef3cd; color: #9a6f00; }
    .badge-red { background: #fde8e8; color: var(--red); }
  </style>
  {% block head %}{% endblock %}
</head>
<body>

<nav>
  <a href="/" class="nav-logo">
    <div class="nav-logo-icon">🎁</div>
    <span class="nav-logo-text">Cesta de Presentes</span>
  </a>
  <div class="nav-links">
    <a href="/#cestas">Cestas</a>
    <a href="/#como-funciona">Como funciona</a>
    <a href="https://wa.me/5511999999999" target="_blank">WhatsApp</a>
  </div>
  <a href="/#cestas" class="nav-cart">🛒 Comprar</a>
</nav>

{% block content %}{% endblock %}

<footer>
  <div class="footer-logo">🎁 Cesta de Presentes</div>
  <p style="margin:8px 0">Presenteie com amor e cuidado</p>
  <p style="margin:16px 0 4px"><a href="mailto:contato@cestadepresentes.com.br">contato@cestadepresentes.com.br</a></p>
  <p><a href="https://wa.me/5511999999999" target="_blank">WhatsApp: (11) 99999-9999</a></p>
  <p style="margin-top:24px;font-size:11px;opacity:.4">© 2024 cestadepresentes.com.br — São Paulo, SP</p>
</footer>

</body>
</html>
