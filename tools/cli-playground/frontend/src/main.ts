import { mount } from "svelte";
import "./theme.css";
import App from "./App.svelte";

const target = document.getElementById("app");
if (!target) throw new Error("The playground mount element is missing");
mount(App, { target });
