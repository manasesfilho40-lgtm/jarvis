import sys
import json
from actions.negotiation_script import negotiation_script_action

def test():
    print("Gerando script de negociação de teste...")
    res = negotiation_script_action({
        "action": "generate",
        "product": "Layout de Ad para Loja de Roupas",
        "price": "R$ 150,00",
        "max_discount": "20%",
        "tone": "persuasivo e amigável"
    })
    print(res)
    
    print("\nCarregando script...")
    loaded = negotiation_script_action({
        "action": "load",
        "product": "Layout de Ad para Loja de Roupas"
    })
    print(loaded)

if __name__ == "__main__":
    test()
