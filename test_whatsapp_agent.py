import sys
import asyncio
from actions.whatsapp_web import WhatsAppWeb

async def main():
    if len(sys.argv) > 1:
        target = sys.argv[1]
    else:
        target = input("Digite o nome ou numero do contato para testar o bot de vendas: ")
        if not target:
            target = "Você mesmo"
    
    print(f"Iniciando Jarvis Negotiation Agent no WhatsApp para: {target}")
    wa = WhatsAppWeb()
    
    try:
        await wa.start()
        await wa.open_chat(target)
        await wa.send_message("Olá! Aqui é o assistente virtual (Jarvis) iniciando os testes de negociação. Pode me enviar uma mensagem para começarmos!")
        await wa.autonomous_loop("Layout de Ad para Loja de Roupas")
    except Exception as e:
        print("Erro no WhatsApp:", e)
    finally:
        await wa.stop()

if __name__ == "__main__":
    asyncio.run(main())
