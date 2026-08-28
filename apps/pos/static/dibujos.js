/* ==========================================================
   Dibujos de los productos.
   Vienen tal cual de las pantallas del local (menu-cafeteria), para que un
   café se vea igual en la caja que en el menú de la pared. Acá se dibujan
   quietos: en la caja puede haber 30 en pantalla y no tiene sentido que
   todos echen vapor.
   Lienzo de 240 x 240. Uso: dibujo({k:"mug", col:"#3A1B0C"})
   ========================================================== */
let _uid = 0;
const uid = () => "u" + (++_uid);

const SOMBRA = '<ellipse cx="120" cy="207" rx="72" ry="10" fill="#000" opacity=".24"/>';

const vapor = (x, y, d) =>
  `<g class="vapor" style="--d:${d}s"><path d="M${x} ${y} c-12 -16 9 -24 -2 -40 c-9 -13 5 -22 -1 -33"
   fill="none" stroke="#FFF3E4" stroke-opacity=".5" stroke-width="5.5" stroke-linecap="round"/></g>`;

const cremaBatida = (cy) => `
  <g>
    <ellipse cx="120" cy="${cy + 6}" rx="36" ry="11" fill="#FFF7EC"/>
    <circle cx="102" cy="${cy - 4}" r="15" fill="#FFF7EC"/>
    <circle cx="122" cy="${cy - 12}" r="17" fill="#FFF7EC"/>
    <circle cx="140" cy="${cy - 4}" r="14" fill="#FFF7EC"/>
    <path d="M120 ${cy - 40} l8 16 -17 0 Z" fill="#FFF7EC"/>
    <path d="M100 ${cy - 10} q20 -12 40 -2" fill="none" stroke="#5A3018" stroke-opacity=".55" stroke-width="4" stroke-linecap="round"/>
  </g>`;

const arteLatte = (cy) => `
  <path d="M120 ${cy - 8} c-9 -7 -22 -2 -18 7 c3 7 13 10 18 12 c5 -2 15 -5 18 -12 c4 -9 -9 -14 -18 -7 Z"
   fill="#C08850" opacity=".5"/>`;

function mug(o) {           /* taza alta: latte, capuchino, americano */
  const liq = o.col || o.liq || "#3A1B0C";
  const sup = o.col || o.foam || liq;
  return `${SOMBRA}
  <path d="M182 108 C218 106 228 154 186 164" fill="none" stroke="#EFDCC4" stroke-width="15" stroke-linecap="round"/>
  <path d="M58 90 L70 180 Q73 196 90 196 L150 196 Q167 196 170 180 L182 90 Z" fill="#F7EADB"/>
  <path d="M152 90 L182 90 L170 180 Q167 196 150 196 L143 196 Z" fill="#DFC7AB" opacity=".6"/>
  <path d="M74 106 L84 174" stroke="#FFFDF8" stroke-opacity=".85" stroke-width="7" stroke-linecap="round"/>
  <ellipse cx="120" cy="90" rx="62" ry="15" fill="#EEDCC6"/>
  <ellipse cx="120" cy="91" rx="53" ry="12.4" fill="#20100A"/>
  <ellipse cx="120" cy="92" rx="51" ry="11.6" fill="${sup}"/>
  ${o.arte ? arteLatte(92) : ""}
  ${o.cacao ? '<circle cx="100" cy="88" r="3" fill="#7A4A28" opacity=".6"/><circle cx="128" cy="94" r="2.6" fill="#7A4A28" opacity=".6"/><circle cx="140" cy="86" r="2.2" fill="#7A4A28" opacity=".6"/><circle cx="112" cy="96" r="2" fill="#7A4A28" opacity=".6"/>' : ""}
  ${o.crema ? cremaBatida(78) : ""}
  ${o.hot ? vapor(94, 74, 0) + vapor(126, 68, 1.5) + vapor(150, 76, 2.9) : ""}`;
}

function taza(o) {          /* taza chica con plato: espresso, cortado */
  const liq = o.col || o.liq || "#2E1408";
  return `${SOMBRA}
  <ellipse cx="120" cy="192" rx="86" ry="15" fill="#E4D2BB"/>
  <ellipse cx="120" cy="188" rx="86" ry="15" fill="#F7EADB"/>
  <ellipse cx="120" cy="187" rx="58" ry="10" fill="#E4D2BB" opacity=".7"/>
  <path d="M166 136 C190 134 196 164 172 170" fill="none" stroke="#EFDCC4" stroke-width="12" stroke-linecap="round"/>
  <path d="M74 124 L84 170 Q86 182 98 182 L142 182 Q154 182 156 170 L166 124 Z" fill="#F7EADB"/>
  <path d="M142 124 L166 124 L156 170 Q154 182 142 182 L136 182 Z" fill="#DFC7AB" opacity=".55"/>
  <path d="M86 136 L94 166" stroke="#FFFDF8" stroke-opacity=".85" stroke-width="6" stroke-linecap="round"/>
  <ellipse cx="120" cy="124" rx="46" ry="11.5" fill="#EEDCC6"/>
  <ellipse cx="120" cy="125" rx="39" ry="9.4" fill="#20100A"/>
  <ellipse cx="120" cy="126" rx="37" ry="8.6" fill="${liq}"/>
  <ellipse cx="120" cy="126" rx="30" ry="6" fill="#B9803F" opacity=".45"/>
  ${o.hot ? vapor(102, 110, .4) + vapor(134, 104, 2.1) : ""}`;
}

function vaso(o) {          /* vaso alto: cold brew, iced latte, tonica */
  const id = uid();
  const arriba = o.col || o.arriba || "#4A2410", abajo = o.abajo || "#3A1B0C";
  const corte = 56 + (202 - 56) * (o.corte === undefined ? .35 : o.corte);
  const forma = "M76 46 L90 190 Q92 202 104 202 L136 202 Q148 202 150 190 L164 46 Z";
  return `${SOMBRA}
  <defs><clipPath id="${id}"><path d="${forma}"/></clipPath></defs>
  <g clip-path="url(#${id})">
    <rect x="60" y="${corte}" width="120" height="150" fill="${abajo}"/>
    <rect x="60" y="52" width="120" height="${corte - 52}" fill="${arriba}"/>
    <ellipse cx="120" cy="${corte}" rx="60" ry="7" fill="${arriba}" opacity=".55"/>
    <ellipse cx="120" cy="56" rx="60" ry="8" fill="#FFFFFF" opacity=".16"/>
    ${o.hielo ? `
      <rect x="90" y="68" width="34" height="30" rx="8" fill="#FFFFFF" opacity=".34" transform="rotate(-14 107 83)"/>
      <rect x="118" y="92" width="32" height="28" rx="8" fill="#FFFFFF" opacity=".28" transform="rotate(18 134 106)"/>
      <rect x="86" y="112" width="30" height="26" rx="7" fill="#FFFFFF" opacity=".3" transform="rotate(8 101 125)"/>` : ""}
    <circle class="burbuja" style="--d:.2s" cx="104" cy="176" r="4" fill="#FFF3E4" opacity=".55"/>
    <circle class="burbuja" style="--d:1.4s" cx="132" cy="182" r="3" fill="#FFF3E4" opacity=".5"/>
    <circle class="burbuja" style="--d:2.6s" cx="118" cy="186" r="3.6" fill="#FFF3E4" opacity=".45"/>
    <path d="M88 60 L100 184" stroke="#FFFFFF" stroke-opacity=".3" stroke-width="9" stroke-linecap="round"/>
  </g>
  <path d="${forma}" fill="#FFFFFF" fill-opacity=".07" stroke="#FFFFFF" stroke-opacity=".5" stroke-width="3.5"/>
  <ellipse cx="120" cy="46" rx="44" ry="11" fill="none" stroke="#FFFFFF" stroke-opacity=".6" stroke-width="3.5"/>
  ${o.bombilla === 0 ? "" : `<rect x="142" y="14" width="12" height="140" rx="6" fill="#F0A94A" transform="rotate(13 148 84)"/>`}
  ${o.adorno === "limon" ? `<g transform="translate(158 40)"><circle r="19" fill="#F2D65C"/><circle r="14" fill="#FBEDA6"/>
      <path d="M0 -14 L0 14 M-14 0 L14 0 M-10 -10 L10 10 M-10 10 L10 -10" stroke="#F2D65C" stroke-width="2.6"/></g>` : ""}
  ${o.adorno === "menta" ? `<g transform="translate(150 34)"><ellipse rx="15" ry="9" fill="#5E9A46" transform="rotate(-24)"/>
      <ellipse rx="13" ry="8" fill="#7CB85F" transform="translate(14 8) rotate(16)"/></g>` : ""}`;
}

function frappe(o) {
  const id = uid(), liq = o.col || o.liq || "#5A3018";
  const forma = "M78 82 L88 190 Q90 204 106 204 L134 204 Q150 204 152 190 L162 82 Z";
  return `${SOMBRA}
  <defs><clipPath id="${id}"><path d="${forma}"/></clipPath></defs>
  <g clip-path="url(#${id})">
    <rect x="60" y="86" width="120" height="130" fill="${liq}"/>
    <rect x="60" y="140" width="120" height="80" fill="#3F2011" opacity=".45"/>
    <circle class="burbuja" style="--d:.6s" cx="110" cy="180" r="3.4" fill="#FFF3E4" opacity=".45"/>
    <circle class="burbuja" style="--d:2.2s" cx="132" cy="184" r="3" fill="#FFF3E4" opacity=".4"/>
    <path d="M90 96 L100 186" stroke="#FFFFFF" stroke-opacity=".26" stroke-width="9" stroke-linecap="round"/>
  </g>
  <path d="${forma}" fill="#FFFFFF" fill-opacity=".07" stroke="#FFFFFF" stroke-opacity=".5" stroke-width="3.5"/>
  ${cremaBatida(72)}
  <rect x="140" y="8" width="12" height="120" rx="6" fill="#C0304A" transform="rotate(14 146 68)"/>`;
}

function croissant(o) {
  const cuerpo = "#DDA25A", sombra = "#C1832F", luz = "#F0C88A";
  const seg = (x, y, rx, ry, rot) =>
    `<g transform="translate(${x} ${y}) rotate(${rot})">
       <ellipse rx="${rx}" ry="${ry}" fill="${cuerpo}"/>
       <ellipse rx="${rx}" ry="${ry}" fill="${sombra}" opacity=".35" transform="translate(4 6)"/>
       <ellipse rx="${rx - 6}" ry="${ry - 7}" fill="${cuerpo}"/>
       <ellipse rx="${rx * .5}" ry="${ry * .34}" fill="${luz}" opacity=".7" transform="translate(-4 -${ry * .42})"/>
     </g>`;
  return `${SOMBRA}
  ${seg(48, 158, 21, 25, -32)}
  ${seg(192, 158, 21, 25, 32)}
  ${seg(80, 132, 27, 33, -16)}
  ${seg(160, 132, 27, 33, 16)}
  ${seg(120, 120, 32, 40, 0)}
  ${o.almendras ? `<g fill="#F4E3C6">
      <ellipse cx="104" cy="96" rx="11" ry="6" transform="rotate(-18 104 96)"/>
      <ellipse cx="130" cy="90" rx="11" ry="6" transform="rotate(12 130 90)"/>
      <ellipse cx="118" cy="106" rx="10" ry="5.4" transform="rotate(-4 118 106)"/></g>
     <g fill="#FFFFFF" opacity=".8"><circle cx="92" cy="112" r="2.4"/><circle cx="146" cy="108" r="2.2"/><circle cx="120" cy="86" r="2"/></g>` : ""}`;
}

function torta(o) {
  const id = uid();
  const glaseado = o.col || o.glaseado || "#C0304A", relleno = o.relleno || "#FBF1E0";
  const forma = "M62 176 Q62 188 76 188 L164 188 Q178 188 178 176 L154 96 Q152 86 142 86 L98 86 Q88 86 86 96 Z";
  return `${SOMBRA}
  <defs><clipPath id="${id}"><path d="${forma}"/></clipPath></defs>
  <g clip-path="url(#${id})">
    <rect x="55" y="140" width="130" height="60" fill="#E0BE86"/>
    <rect x="55" y="112" width="130" height="30" fill="${relleno}"/>
    <rect x="55" y="86" width="130" height="27" fill="${glaseado}"/>
    <rect x="55" y="150" width="130" height="10" fill="#CBA469" opacity=".7"/>
    <path d="M80 113 q14 22 26 2 q12 20 26 0 q12 20 26 -2 L182 190 L55 190 Z" fill="none"/>
    <path d="M78 112 q12 20 24 3 q12 20 26 1 q12 20 26 -3 l0 -18 -76 0 Z" fill="${glaseado}"/>
  </g>
  <path d="${forma}" fill="none" stroke="#000" stroke-opacity=".12" stroke-width="2"/>
  <g transform="translate(120 74)">
    <circle r="13" fill="${glaseado}"/><circle r="6" cx="-11" cy="7" fill="${glaseado}" opacity=".85"/>
    <circle r="4" cx="6" cy="-9" fill="#FFFFFF" opacity=".35"/>
    <ellipse rx="12" ry="6" cy="-12" cx="12" fill="#5E9A46" transform="rotate(-22 12 -12)"/>
  </g>`;
}

function brownie(o) {
  return `${SOMBRA}
  <path d="M64 124 L88 100 L194 100 L170 124 Z" fill="#7A4E2C"/>
  <path d="M170 124 L194 100 L194 160 L170 184 Z" fill="#3A2013"/>
  <path d="M64 124 L170 124 L170 176 Q170 186 160 186 L74 186 Q64 186 64 176 Z" fill="#4E2B15"/>
  <path d="M64 124 L170 124 L170 133 L64 133 Z" fill="#8A5F36" opacity=".55"/>
  <g fill="#B0813F">
    <circle cx="112" cy="110" r="7"/><circle cx="148" cy="114" r="6"/><circle cx="132" cy="104" r="5"/>
  </g>
  <g fill="#F0C88A" opacity=".55">
    <circle cx="96" cy="150" r="3.4"/><circle cx="140" cy="162" r="3"/><circle cx="118" cy="142" r="2.6"/>
  </g>
  <path d="M76 138 L76 174" stroke="#FFFFFF" stroke-opacity=".12" stroke-width="7" stroke-linecap="round"/>`;
}

function alfajor(o) {
  return `${SOMBRA}
  <rect x="58" y="140" width="124" height="30" rx="15" fill="#DFB77E"/>
  <rect x="58" y="116" width="124" height="28" rx="10" fill="#B0742F"/>
  <rect x="58" y="88" width="124" height="34" rx="17" fill="#F0D5A4"/>
  <rect x="58" y="88" width="124" height="14" rx="7" fill="#F8E6C4"/>
  <g fill="#FFF7EC">
    <circle cx="66" cy="130" r="4"/><circle cx="88" cy="134" r="3.4"/><circle cx="112" cy="130" r="3.8"/>
    <circle cx="138" cy="134" r="3.4"/><circle cx="162" cy="130" r="4"/><circle cx="176" cy="134" r="3"/>
  </g>
  <g fill="#FFFFFF" opacity=".75">
    <circle cx="92" cy="98" r="2.6"/><circle cx="124" cy="94" r="2.2"/><circle cx="152" cy="100" r="2.4"/>
  </g>`;
}

const ART = { mug, taza, vaso, frappe, croissant, torta, brownie, alfajor };
/* ==========================================================
   Recetas: un nombre simple -> los parámetros del dibujo.
   Existen porque el punto de venta guarda UN campo (`dibujo`) y no toda la
   ficha del dibujo. Así el dueño elige "Capuchino" en una lista y el vaso
   sale con su espuma, sin tener que entender de parámetros.
   ========================================================== */
const RECETAS = {
  "taza":            { k: "taza", liq: "#2E1408", hot: 1 },
  "taza-cortado":    { k: "taza", liq: "#7A4A28", hot: 1 },
  "mug":             { k: "mug", liq: "#3B1C0C", hot: 1 },
  "mug-espuma":      { k: "mug", liq: "#6B4022", foam: "#F3E2CC", cacao: 1, hot: 1 },
  "mug-arte":        { k: "mug", liq: "#A97544", foam: "#F0DCC0", arte: 1, hot: 1 },
  "mug-crema":       { k: "mug", liq: "#3A1B0C", crema: 1, hot: 1 },
  "vaso":            { k: "vaso", arriba: "#4A2410", abajo: "#3A1B0C", corte: .2, hielo: 1 },
  "vaso-leche":      { k: "vaso", arriba: "#6B4022", abajo: "#F1E1CC", corte: .38, hielo: 1 },
  "vaso-limon":      { k: "vaso", arriba: "#B4712F", abajo: "#EFD9A8", corte: .3, hielo: 1, adorno: "limon" },
  "vaso-verde":      { k: "vaso", arriba: "#8FB861", abajo: "#F1E7D4", corte: .42, hielo: 1 },
  "vaso-menta":      { k: "vaso", arriba: "#D9E27A", abajo: "#EDF0B4", corte: .35, hielo: 1, adorno: "menta" },
  "frappe":          { k: "frappe", liq: "#5A3018" },
  "croissant":       { k: "croissant" },
  "croissant-almendras": { k: "croissant", almendras: 1 },
  "torta":           { k: "torta", glaseado: "#C0304A", relleno: "#FBF1E0" },
  "torta-manzana":   { k: "torta", glaseado: "#D89A4E", relleno: "#F3DFC0" },
  "brownie":         { k: "brownie" },
  "alfajor":         { k: "alfajor" },
};

/* En la caja el vapor y las burbujas van quietos: sin animación. */
const dibujo = (a) => {
  const receta = RECETAS[(a && a.k) || "mug"] || RECETAS.mug;
  const art = Object.assign({}, receta);
  if (a && a.col) art.col = a.col;          // el color elegido manda sobre la receta
  // Recorte: el lienzo de 240 tiene mucho aire arriba y a los lados, y en un
  // azulejo chico eso hace que el dibujo se vea perdido. Mostramos solo la parte
  // donde realmente hay algo dibujado.
  return `<svg class="art" viewBox="22 38 196 182" preserveAspectRatio="xMidYMid meet" aria-hidden="true">${(ART[art.k] || mug)(art)}</svg>`;
};
