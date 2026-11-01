import {configureStore,createSlice,PayloadAction} from '@reduxjs/toolkit';
type State={view:string;collections:string[];toast:string};
const slice=createSlice({name:'app',initialState:{view:'dashboard',collections:[],toast:''} as State,reducers:{view:(s,a:PayloadAction<string>)=>{s.view=a.payload},collections:(s,a:PayloadAction<string[]>)=>{s.collections=a.payload},toast:(s,a:PayloadAction<string>)=>{s.toast=a.payload}}});
export const actions=slice.actions;export const store=configureStore({reducer:{app:slice.reducer}});export type RootState=ReturnType<typeof store.getState>;
