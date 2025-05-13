import streamlit as st



st.set_page_config(
    page_title="Times",
    page_icon="🏃🏼",
    layout="wide"
)

# st.write('#Em Construção')

st.markdown('# Análise Times Por Temporada')


# df_liga_anos = st.session_state["data_ligas_anos"]

df_times_anos = st.session_state["data_times_anos"]


anos = df_times_anos['Ano'].unique().tolist()
anos.insert(0, "Todos")  # Adiciona a opção "Todos" no início da lista


temporada = st.sidebar.selectbox("Ano",anos)


# Filtrar o DataFrame com base na seleção
if temporada == "Todos":
    df_filtrado_anos = df_times_anos
    times = df_times_anos["Time"].unique().tolist()
    times.insert(0, "Todos")
    times = st.sidebar.selectbox("Times_Seleção", times)
    if times == "Todos":
        # df_filtrado_anos
        pass
    else:
        df_filtrado_anos = df_times_anos[df_times_anos['Time'] == times]
    #     df_filtrado_anos = df_ligas_anos[df_ligas_anos['temporada'] == temporada and df_liga_anos[df_liga_anos['liga'] == ligas]]
else:
    df_filtrado_anos = df_times_anos[df_times_anos['Ano'] == temporada]

    times = df_times_anos["Time"].unique()
    # # ligas.insert(0, "Todos")
    times = st.sidebar.selectbox("Liga_Seleção", times)
    df_filtrado_anos = df_filtrado_anos[df_filtrado_anos['Time'] == times]

columns = ['Ano',"Tipo_Campeonato",'Campeonato',"Time",'Time_image','Total_Jogos',
           '%_Over05FT','%_Over15FT','%_Over25FT','%_Over35FT']

st.dataframe(df_filtrado_anos[columns],
    column_config={ 
    "Time_image": st.column_config.ImageColumn('Escudo'),
    })
 