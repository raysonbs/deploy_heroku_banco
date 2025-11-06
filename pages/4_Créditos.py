import streamlit as st
import pandas as pd
import numpy as np

st.set_page_config(layout="wide") # Opcional, mas recomendado para usar a largura total da página

st.title("DataFrame Ocupando Largura Máxima")

# Criando um DataFrame de exemplo
data = {
    'coluna_a': np.random.rand(10),
    'coluna_b': np.random.randint(1, 100, 10),
    'coluna_c': [f'Texto longo para demonstração {i}' for i in range(10)],
    'coluna_d': pd.to_datetime(pd.date_range('2023-01-01', periods=10))
}
df_exemplo = pd.DataFrame(data)

st.write("---")
st.header("DataFrame com `use_container_width=True`")
st.dataframe(df_exemplo, use_container_width=True) # <<< AQUI ESTÁ O TRUQUE!

st.write("---")
st.header("DataFrame sem `use_container_width` (padrão)")
st.dataframe(df_exemplo)

st.write("Observe a diferença na largura dos dois DataFrames acima.")