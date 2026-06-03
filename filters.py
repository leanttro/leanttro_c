import smtplib
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

def send_email(to: str, subject: str, html: str):
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = f"{os.getenv('EMAIL_FROM_NAME', 'Cesta de Presentes')} <{os.getenv('EMAIL_FROM')}>"
        msg['To'] = to
        msg.attach(MIMEText(html, 'html'))

        with smtplib.SMTP(os.getenv('SMTP_HOST', 'smtp.gmail.com'), int(os.getenv('SMTP_PORT', 587))) as server:
            server.starttls()
            server.login(os.getenv('SMTP_USER'), os.getenv('SMTP_PASSWORD'))
            server.sendmail(os.getenv('EMAIL_FROM'), to, msg.as_string())
        return True
    except Exception as e:
        print(f"Erro ao enviar e-mail: {e}")
        return False


def email_pedido_confirmado(pedido, itens):
    base_url = os.getenv('BASE_URL', 'https://cestadepresentes.com.br')
    
    itens_html = "".join([
        f"<tr><td style='padding:8px;border-bottom:1px solid #f0e6d3'>{i.nome_produto}</td>"
        f"<td style='padding:8px;border-bottom:1px solid #f0e6d3;text-align:center'>{i.quantidade}</td>"
        f"<td style='padding:8px;border-bottom:1px solid #f0e6d3;text-align:right'>R$ {float(i.preco_unitario):.2f}</td></tr>"
        for i in itens
    ])

    entrega_html = (
        f"<p>📦 <strong>Envio para:</strong> {pedido.endereco} — {pedido.servico_frete} (R$ {float(pedido.valor_frete):.2f})</p>"
        if pedido.tipo_entrega == 'envio'
        else "<p>🛍️ <strong>Retirada no local</strong> — entraremos em contato para combinar o horário.</p>"
    )

    html = f"""
    <!DOCTYPE html><html lang="pt-br"><head><meta charset="UTF-8"></head>
    <body style="margin:0;padding:0;background:#fdf6ee;font-family:Georgia,serif">
      <table width="100%" cellpadding="0" cellspacing="0">
        <tr><td align="center" style="padding:40px 20px">
          <table width="600" cellpadding="0" cellspacing="0" style="background:#fff;border-radius:16px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.08)">
            
            <tr><td style="background:linear-gradient(135deg,#c0392b,#e74c3c);padding:40px;text-align:center">
              <h1 style="color:#fff;margin:0;font-size:28px;letter-spacing:1px">🎁 Pedido Confirmado!</h1>
              <p style="color:rgba(255,255,255,0.85);margin:8px 0 0">Pedido #{pedido.numero}</p>
            </td></tr>

            <tr><td style="padding:32px 40px">
              <p style="font-size:16px;color:#5a3e2b">Olá, <strong>{pedido.nome.split()[0]}</strong>! 🎉</p>
              <p style="color:#7a6152;line-height:1.6">Seu pedido foi confirmado e já estamos preparando sua cesta com muito carinho.</p>

              <table width="100%" cellpadding="0" cellspacing="0" style="margin:24px 0;border:1px solid #f0e6d3;border-radius:8px;overflow:hidden">
                <tr style="background:#fdf6ee">
                  <th style="padding:10px 8px;text-align:left;color:#5a3e2b;font-size:12px;text-transform:uppercase">Produto</th>
                  <th style="padding:10px 8px;text-align:center;color:#5a3e2b;font-size:12px;text-transform:uppercase">Qtd</th>
                  <th style="padding:10px 8px;text-align:right;color:#5a3e2b;font-size:12px;text-transform:uppercase">Valor</th>
                </tr>
                {itens_html}
                <tr style="background:#fdf6ee">
                  <td colspan="2" style="padding:12px 8px;font-weight:bold;color:#5a3e2b">Total</td>
                  <td style="padding:12px 8px;text-align:right;font-weight:bold;color:#c0392b;font-size:18px">R$ {float(pedido.valor_total):.2f}</td>
                </tr>
              </table>

              {entrega_html}

              <p style="color:#7a6152;line-height:1.6">Qualquer dúvida, responda este e-mail ou fale pelo WhatsApp.</p>
              <p style="color:#5a3e2b;margin-top:32px">Com carinho,<br><strong>Equipe Cesta de Presentes 🎀</strong></p>
            </td></tr>

            <tr><td style="background:#fdf6ee;padding:20px;text-align:center">
              <p style="color:#b0937a;font-size:12px;margin:0">{base_url}</p>
            </td></tr>
          </table>
        </td></tr>
      </table>
    </body></html>
    """
    return send_email(pedido.email, f"🎁 Pedido #{pedido.numero} confirmado — Cesta de Presentes", html)


def email_pedido_enviado(pedido):
    html = f"""
    <!DOCTYPE html><html lang="pt-br"><head><meta charset="UTF-8"></head>
    <body style="margin:0;padding:0;background:#fdf6ee;font-family:Georgia,serif">
      <table width="100%" cellpadding="0" cellspacing="0">
        <tr><td align="center" style="padding:40px 20px">
          <table width="600" cellpadding="0" cellspacing="0" style="background:#fff;border-radius:16px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.08)">
            <tr><td style="background:linear-gradient(135deg,#27ae60,#2ecc71);padding:40px;text-align:center">
              <h1 style="color:#fff;margin:0;font-size:28px">📦 Sua cesta foi enviada!</h1>
              <p style="color:rgba(255,255,255,0.85);margin:8px 0 0">Pedido #{pedido.numero}</p>
            </td></tr>
            <tr><td style="padding:32px 40px">
              <p style="font-size:16px;color:#5a3e2b">Olá, <strong>{pedido.nome.split()[0]}</strong>! 🚚</p>
              <p style="color:#7a6152;line-height:1.6">Sua cesta está a caminho! Rastreie pelo código abaixo:</p>
              <div style="background:#fdf6ee;border:2px dashed #e8c9a0;border-radius:8px;padding:20px;text-align:center;margin:20px 0">
                <p style="margin:0;font-size:12px;color:#7a6152;text-transform:uppercase;letter-spacing:1px">Código de Rastreio</p>
                <p style="margin:8px 0 0;font-size:24px;font-weight:bold;color:#c0392b;letter-spacing:3px">{pedido.codigo_rastreio}</p>
              </div>
              <p style="color:#7a6152">Acesse <a href="https://rastreamento.correios.com.br" style="color:#c0392b">correios.com.br</a> para acompanhar.</p>
              <p style="color:#5a3e2b;margin-top:32px">Com carinho,<br><strong>Equipe Cesta de Presentes 🎀</strong></p>
            </td></tr>
          </table>
        </td></tr>
      </table>
    </body></html>
    """
    return send_email(pedido.email, f"📦 Sua cesta foi enviada! Código: {pedido.codigo_rastreio}", html)


def email_novo_pedido_admin(pedido, itens):
    """Notifica o lojista sobre novo pedido"""
    admin_email = os.getenv('SMTP_USER')
    itens_txt = "\n".join([f"- {i.nome_produto} x{i.quantidade} = R$ {float(i.preco_unitario * i.quantidade):.2f}" for i in itens])
    
    html = f"""
    <h2>🛍️ Novo Pedido: #{pedido.numero}</h2>
    <p><strong>Cliente:</strong> {pedido.nome} ({pedido.email}) {pedido.telefone or ''}</p>
    <p><strong>Total:</strong> R$ {float(pedido.valor_total):.2f}</p>
    <p><strong>Entrega:</strong> {'Retirada' if pedido.tipo_entrega == 'retirada' else pedido.endereco}</p>
    <p><strong>Itens:</strong><br><pre>{itens_txt}</pre></p>
    {'<p><strong>Mensagem:</strong> ' + pedido.mensagem + '</p>' if pedido.mensagem else ''}
    """
    return send_email(admin_email, f"🛍️ Novo pedido #{pedido.numero} — {pedido.nome}", html)
