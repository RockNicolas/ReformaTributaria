"""Códigos de erro da calculadora oficial (REG-xxx) -> o que o usuário deve fazer.

As mensagens do motor já vêm em português; o valor aqui é a AÇÃO prática.
Fonte dos códigos: ProblemType.java do repositório calculadora-rtc-regime-regular.
"""

SUGESTOES: dict[str, str] = {
    "REG-001": "Informar só NCM (produto) ou só NBS (serviço) no item, nunca os dois.",
    "REG-002": "Conferir o NCM no cadastro do produto; pode estar digitado errado ou fora de vigência.",
    "REG-003": "Conferir o NBS no cadastro do serviço; pode estar digitado errado ou fora de vigência.",
    "REG-004": "Corrigir o CST de IBS/CBS do item (3 dígitos) para um valor existente na data da operação.",
    "REG-005": "Corrigir o cClassTrib (6 dígitos) do item; o código não existe na base vigente.",
    "REG-006": "O cClassTrib não pertence a esse CST: escolher um par CST + cClassTrib compatível.",
    "REG-007": "Revisar NCM/NBS e a classificação tributária; há inconsistência entre eles.",
    "REG-008": "Revisar a classificação do item; não há tratamento para essa combinação de dados.",
    "REG-009": "Esse CST exige o grupo de tributação regular: configurar no ERP/emissor.",
    "REG-010": "Classificação incompatível com operação suspensa: revisar CST/cClassTrib do item.",
    "REG-011": "O NCM não está vinculado a esse cClassTrib: trocar a classificação ou revisar o NCM do produto.",
    "REG-012": "O NBS não está vinculado a esse cClassTrib: trocar a classificação ou revisar o NBS do serviço.",
    "REG-013": "Informar os dados do Imposto Seletivo; a classificação escolhida exige.",
    "REG-014": "Remover os dados do Imposto Seletivo; a classificação escolhida não prevê incidência.",
    "REG-015": "Preencher o NCM completo (8 dígitos) no cadastro do produto.",
    "REG-016": "Preencher o NBS completo no cadastro do serviço.",
    "REG-018": "O município informado não pertence à UF: corrigir o código do município (IBGE).",
    "REG-019": "Corrigir o código IBGE do município.",
    "REG-020": "Corrigir a UF da operação.",
    "REG-021": "Informar a data do fato gerador.",
    "REG-022": "Remover o grupo de tributação regular; esse CST não o exige.",
    "REG-023": "Revisar os dados do item; erro genérico de validação.",
    "REG-024": "Revisar o campo apontado no detalhe do erro.",
    "REG-025": "Informar a base de cálculo de CBS/IBS do item.",
    "REG-026": "Corrigir a base de cálculo: deve ser igual à base do Imposto Seletivo somada ao próprio IS.",
    "REG-027": "Corrigir a base de cálculo: não pode ser menor que a base do Imposto Seletivo.",
    "REG-028": "Tipo de documento fiscal inválido ou fora de vigência na data da operação.",
    "REG-029": "Classificação não permitida para este tipo de documento: trocar o cClassTrib.",
    "REG-030": "NCM/NBS não aceito para essa classificação neste tipo de documento: revisar o cadastro.",
    "REG-031": "Este tipo de documento não admite NCM/NBS: remover do item.",
    "REG-032": "Item sujeito a Imposto Seletivo não pode ir neste tipo de documento: revisar emissão.",
    "REG-033": "Informar NCM ou NBS completo: a classificação escolhida exige.",
    "REG-034": "A base de cálculo declarada diverge da calculada: revisar valores do item.",
    "REG-035": "Alíquota do Imposto Seletivo ainda não definida em lei: informar a alíquota de simulação.",
    "REG-036": "Fato gerador até 2026: não enviar alíquotas nominais (a calculadora resolve sozinha).",
    "REG-037": "Fato gerador a partir de 2027: informar as alíquotas nominais (CBS, IBS UF, IBS município).",
    "REG-038": "Tipo de documento ainda não tratado pela calculadora oficial.",
}

PADRAO = "Revisar NCM/NBS, CST e cClassTrib do item; se persistir, acionar o suporte."


def sugestao_para(codigo: str) -> str:
    return SUGESTOES.get(codigo, PADRAO)
