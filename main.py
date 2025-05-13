import streamlit as st
import pandas as pd
import os



df = pd.read_csv(r'D:\Projetos\Deploy_Heroku_Banco\CLEAN_FIFA23_official_data.csv')
# df

nomes = df['Name'].unique().tolist()
nomes.insert(0, "Todos")  # Adiciona a opção "Todos" no início da lista


Nome = st.sidebar.selectbox("Nome",nomes)

if Nome == "Todos":
    df = df
    df

else:
    df = df[df['Name'] == Nome]
    df


st.write('Teste')




# username = os.getenv('username')
# password = os.getenv('password')
# host = os.getenv('host')
# port = os.getenv('port')
# database = os.getenv('database')