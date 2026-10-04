/* ==========================================================
   Dibujos de los productos.
   Vienen tal cual de las pantallas del local (menu-cafeteria), para que un
   café se vea igual en la caja que en el menú de la pared. Acá se dibujan
   quietos: en la caja puede haber 30 en pantalla y no tiene sentido que
   todos echen vapor.
   Lienzo de 240 x 240. Uso: dibujo({k:"mug", col:"#3A1B0C"})

   TODO va dentro de una función y afuera sale UNA sola cosa: `dibujo`. Antes
   este archivo declaraba sus ~100 nombres sueltos en el ámbito global (`ART`,
   `mug`, `taza`, `_uid`…). Mientras solo lo cargaba la caja no molestaba, pero
   al cargarlo también la pantalla del local —que tiene sus propios `ART`, `mug`
   y `_uid`— los `const` chocaban y el navegador tiraba abajo el script ENTERO:
   la pantalla quedaba en negro. Una biblioteca no puede ensuciar la casa de
   quien la usa.
   ========================================================== */
(function () {
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

/* ==========================================================
   Segunda familia de dibujos: panadería, envases y comida.
   Mismo lienzo de 240x240, misma paleta y mismo apoyo alrededor de y=195 que
   los de arriba. Si un dibujo nuevo se ve de otra familia, está mal aunque sea
   bonito: los mismos iconos se usan en la caja y en las pantallas del local.
   ========================================================== */

const MASA = "#D9A15B", MASA_OSC = "#B9813C", MASA_LUZ = "#F0C88A", MIGA = "#F6E7C8";

/* ---------- colores a medida (la bolsa de café va del color que elija el dueño) ----------
   El color viene de la base del local: se valida antes de pegarlo en el SVG, y
   si no es un #hex válido se usa el de siempre. */
const hexOk = (c, def) => {
  const m = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i.exec(String(c || "").trim());
  if (!m) return def.toLowerCase();
  const h = m[1].length === 3 ? m[1].split("").map((x) => x + x).join("") : m[1];
  return "#" + h.toLowerCase();
};
const mezcla = (c, otro, t) => {
  const a = [1, 3, 5].map((i) => parseInt(c.slice(i, i + 2), 16));
  const b = [1, 3, 5].map((i) => parseInt(otro.slice(i, i + 2), 16));
  return "#" + a.map((v, i) => Math.round(v + (b[i] - v) * t).toString(16).padStart(2, "0")).join("");
};
const oscuro = (c, t) => mezcla(c, "#000000", t);
const claro = (c, t) => mezcla(c, "#FFFFFF", t);

function pan(o) {                 /* marraqueta, hallulla, amasado, baguette, ciabatta, integral, frica */
  const t = o.tipo || "marraqueta";
  const ENARINA = "#FFF6E2";
  if (t === "baguette") {
    /* dos baguettes en diagonal: lo largo y los cortes son lo que la distingue */
    const una = (dy) => `
      <g transform="translate(0 ${dy})">
        <path d="M24 146 Q28 124 56 124 H184 Q212 124 216 146 Q212 168 184 168 H56 Q28 168 24 146 Z" fill="${MASA}"/>
        <path d="M24 148 Q28 168 56 168 H184 Q212 168 216 148 Q200 160 120 160 Q40 160 24 148 Z" fill="${MASA_OSC}" opacity=".4"/>
        <path d="M40 133 H200" stroke="${MASA_LUZ}" stroke-width="7" stroke-linecap="round" opacity=".65"/>
        ${[62, 96, 130, 164].map((x) => `
          <ellipse cx="${x}" cy="141" rx="14" ry="5.6" fill="#F6DFA8" transform="rotate(62 ${x} 141)"/>
          <ellipse cx="${x}" cy="141" rx="14" ry="5.6" fill="none" stroke="${MASA_OSC}" stroke-width="2.4" opacity=".8" transform="rotate(62 ${x} 141)"/>`).join("")}
      </g>`;
    return `${SOMBRA}
    <g transform="rotate(-20 120 140) translate(0 -8)">${una(-24)}${una(14)}</g>`;
  }
  if (t === "hallulla") {
    /* disco plano y pálido, picado con tenedor: se lee redondo y chato */
    const puntos = [];
    [[0, 0, 1], [26, 15, 6], [52, 30, 10]].forEach(([rx, ry, n]) => {
      for (let i = 0; i < n; i++) {
        const a = (i / n) * 2 * Math.PI + (rx ? .3 : 0);
        puntos.push(`<circle cx="${(120 + Math.cos(a) * rx).toFixed(1)}" cy="${(138 + Math.sin(a) * ry).toFixed(1)}" r="3.4"/>`);
      }
    });
    return `${SOMBRA}
    <ellipse cx="120" cy="158" rx="86" ry="42" fill="#B9813C"/>
    <path d="M34 150 V158 Q34 200 120 200 Q206 200 206 158 V150 Z" fill="#C48F4A"/>
    <ellipse cx="120" cy="146" rx="86" ry="42" fill="#E6B567"/>
    <ellipse cx="120" cy="140" rx="78" ry="36" fill="#EFC884"/>
    <ellipse cx="104" cy="124" rx="40" ry="11" fill="#FBE3B0" opacity=".7"/>
    <g fill="#A8742F" opacity=".75">${puntos.join("")}</g>`;
  }
  if (t === "amasado") {
    /* bollo alto y redondo, enharinado, con la marca de la mano arriba */
    return `${SOMBRA}
    <path d="M44 172 C38 112 82 80 120 80 C158 80 202 112 196 172 Q196 198 120 198 Q44 198 44 172 Z" fill="#CF8F46"/>
    <path d="M44 172 Q44 198 120 198 Q196 198 196 172 Q170 186 120 186 Q70 186 44 172 Z" fill="#9C6628" opacity=".45"/>
    <path d="M56 150 C60 112 90 92 120 92 C150 92 180 112 184 150 C160 128 80 128 56 150 Z" fill="#E0A55B"/>
    <path d="M78 122 Q120 104 162 122" fill="none" stroke="#A8742F" stroke-width="5" stroke-linecap="round" opacity=".6"/>
    <path d="M96 140 Q120 130 144 140" fill="none" stroke="#A8742F" stroke-width="4" stroke-linecap="round" opacity=".45"/>
    <g fill="${ENARINA}" opacity=".7">
      <ellipse cx="98" cy="108" rx="14" ry="6" transform="rotate(-24 98 108)"/>
      <ellipse cx="142" cy="104" rx="10" ry="4.6" transform="rotate(20 142 104)"/>
      <circle cx="128" cy="150" r="3"/><circle cx="82" cy="156" r="2.6"/><circle cx="160" cy="146" r="2.4"/>
    </g>`;
  }
  if (t === "ciabatta") {
    /* plana, alargada, con harina y burbujas grandes: la zapatilla */
    return `${SOMBRA}
    <g transform="rotate(-6 120 146)">
      <path d="M26 156 Q22 120 62 114 Q120 104 184 114 Q220 122 214 156 Q210 196 168 198 Q110 204 62 198 Q28 192 26 156 Z" fill="#B88A4A"/>
      <path d="M26 150 Q22 114 62 108 Q120 98 184 108 Q220 116 214 150 Q210 184 168 186 Q110 192 62 186 Q28 180 26 150 Z" fill="#E4BC78"/>
      <path d="M40 130 Q70 114 120 112 Q170 112 200 128 Q150 120 100 124 Q60 128 40 130 Z" fill="#F6DEAC" opacity=".8"/>
      <g fill="${ENARINA}" opacity=".75">
        <ellipse cx="78" cy="140" rx="22" ry="9" transform="rotate(-8 78 140)"/>
        <ellipse cx="150" cy="134" rx="26" ry="8" transform="rotate(6 150 134)"/>
        <ellipse cx="116" cy="164" rx="30" ry="8" transform="rotate(-3 116 164)"/>
        <ellipse cx="184" cy="156" rx="12" ry="6"/>
      </g>
      <g fill="#A6772F" opacity=".8">
        <ellipse cx="62" cy="152" rx="6" ry="3.6"/><ellipse cx="102" cy="144" rx="7.4" ry="4"/>
        <ellipse cx="132" cy="156" rx="5.4" ry="3.2"/><ellipse cx="168" cy="146" rx="6.6" ry="3.6"/>
        <ellipse cx="92" cy="172" rx="5" ry="3"/><ellipse cx="148" cy="174" rx="6.4" ry="3.4"/>
      </g>
    </g>`;
  }
  if (t === "integral") {
    /* molde oscuro con una rebanada al frente y semillas */
    const semillas = (x, y, s) => `<g fill="#F0DCBC" opacity=".9" transform="translate(${x} ${y}) scale(${s})">
      <ellipse cx="0" cy="0" rx="5" ry="2.6" transform="rotate(-22)"/>
      <ellipse cx="22" cy="-6" rx="5" ry="2.6" transform="rotate(14)"/>
      <ellipse cx="44" cy="2" rx="5" ry="2.6" transform="rotate(-8)"/>
      <ellipse cx="10" cy="14" rx="4.6" ry="2.4" transform="rotate(30)"/>
      <ellipse cx="34" cy="14" rx="4.6" ry="2.4" transform="rotate(-26)"/></g>`;
    return `${SOMBRA}
    <g transform="translate(14 20) scale(.9)">
    <path d="M30 186 V120 Q30 88 62 86 Q94 84 126 86 Q158 88 158 120 V186 Q158 198 146 198 H42 Q30 198 30 186 Z" fill="#7A4F26"/>
    <path d="M30 150 V186 Q30 198 42 198 H146 Q158 198 158 186 V150 Q94 164 30 150 Z" fill="#5E3A19" opacity=".5"/>
    <path d="M38 104 Q94 92 150 104" fill="none" stroke="#A9743C" stroke-width="8" stroke-linecap="round" opacity=".55"/>
    ${semillas(52, 108, 1.1)}
    <path d="M118 198 V156 Q118 126 146 124 Q174 122 202 124 Q226 128 226 156 V198 Z" fill="#8E5F2E"/>
    <path d="M126 198 V158 Q126 134 148 132 Q174 130 196 132 Q218 134 218 158 V198 Z" fill="#D4AB6C"/>
    <path d="M126 168 Q172 178 218 168 V198 H126 Z" fill="#B88A4A" opacity=".45"/>
    <g fill="#8B5E2A" opacity=".8">
      <circle cx="146" cy="152" r="2.8"/><circle cx="170" cy="146" r="2.8"/><circle cx="194" cy="154" r="2.8"/>
      <circle cx="158" cy="172" r="2.6"/><circle cx="184" cy="170" r="2.6"/><circle cx="204" cy="140" r="2.4"/>
    </g></g>`;
  }
  if (t === "frica") {
    /* pan de hamburguesa: tapa abovedada con sésamo y base más chata */
    const ses = [[88, 106, -20], [112, 98, 10], [136, 104, -14], [158, 114, 24], [100, 124, 16],
                 [126, 122, -26], [148, 130, 8], [76, 128, -8], [168, 136, -18], [114, 140, 20]];
    return `${SOMBRA}
    <path d="M52 160 H188 Q188 192 164 196 H76 Q52 192 52 160 Z" fill="#E0AB62"/>
    <path d="M52 168 H188 Q186 190 164 194 H76 Q54 190 52 168 Z" fill="#B9813C" opacity=".4"/>
    <path d="M48 156 H192 V166 Q120 176 48 166 Z" fill="${MIGA}"/>
    <path d="M40 154 Q38 84 120 80 Q202 84 200 154 Q120 166 40 154 Z" fill="#D58F36"/>
    <path d="M40 148 Q42 156 120 162 Q198 156 200 148 Q196 160 120 166 Q44 160 40 148 Z" fill="#A86A1F" opacity=".55"/>
    <path d="M58 122 Q64 96 100 90" fill="none" stroke="#F3C676" stroke-width="9" stroke-linecap="round" opacity=".7"/>
    <g fill="#FFF3D6">${ses.map(([x, y, r]) => `<ellipse cx="${x}" cy="${y}" rx="5.6" ry="3" transform="rotate(${r} ${x} ${y})"/>`).join("")}</g>`;
  }
  /* marraqueta: cuatro gajos pegados (dos y dos), con la raya larga y la cruzada bien marcadas */
  const lomo = (x, y, rx, ry) => `
    <ellipse cx="${x}" cy="${y}" rx="${rx}" ry="${ry}" fill="#C98F43"/>
    <ellipse cx="${x}" cy="${y + 7}" rx="${rx}" ry="${ry - 8}" fill="#8E5A1E" opacity=".28"/>
    <ellipse cx="${x - 6}" cy="${y - 12}" rx="${rx * .55}" ry="${ry * .34}" fill="${MASA_LUZ}" opacity=".7"/>`;
  return `${SOMBRA}
  ${lomo(80, 156, 44, 38)}
  ${lomo(160, 156, 44, 38)}
  ${lomo(80, 120, 42, 34)}
  ${lomo(160, 120, 42, 34)}
  <path d="M120 84 V194" stroke="#7A4A16" stroke-width="8" stroke-linecap="round" opacity=".85"/>
  <path d="M40 138 H200" stroke="#7A4A16" stroke-width="7" stroke-linecap="round" opacity=".65"/>
  <g fill="${ENARINA}" opacity=".6"><circle cx="64" cy="112" r="2.6"/><circle cx="100" cy="104" r="2.2"/><circle cx="176" cy="108" r="2.6"/><circle cx="188" cy="160" r="2.2"/><circle cx="62" cy="168" r="2.2"/><circle cx="138" cy="172" r="2.4"/></g>`;
}

function sandwich(o) {            /* sándwich, churrasco, wrap, completo */
  if (o.tipo === "wrap") {
    return `${SOMBRA}
    <g transform="rotate(-14 120 140)">
      <path d="M78 76 h84 q16 0 16 16 v92 q0 18 -18 18 h-80 q-18 0 -18 -18 V92 q0 -16 16 -16 Z"
            fill="#EBD7AE"/>
      <path d="M78 76 h84 q16 0 16 16 v18 h-116 V92 q0 -16 16 -16 Z" fill="#F3E6CB"/>
      <path d="M64 118 h112 v16 h-112 Z" fill="#8FB861"/>
      <path d="M64 138 h112 v14 h-112 Z" fill="#C0304A" opacity=".8"/>
      <path d="M64 156 h112 v12 h-112 Z" fill="#F0C86A"/>
      <path d="M92 84 q28 -10 56 0" fill="none" stroke="#D8C193" stroke-width="4" stroke-linecap="round"/>
    </g>`;
  }
  const relleno = o.relleno || "#C0304A";
  return `${SOMBRA}
  <path d="M44 150 q0 -46 76 -46 q76 0 76 46 Z" fill="${MASA}"/>
  <path d="M50 124 q40 -22 70 -22" fill="none" stroke="${MASA_LUZ}"
        stroke-width="7" stroke-linecap="round" opacity=".6"/>
  <rect x="44" y="150" width="152" height="12" fill="#8FB861"/>
  <rect x="44" y="160" width="152" height="14" fill="${relleno}"/>
  ${o.queso ? '<path d="M44 174 h152 l-16 14 -20 -10 -22 12 -20 -10 -22 12 -20 -10 -18 10 -14 -8 Z" fill="#F0C86A"/>' : ""}
  <path d="M44 ${o.queso ? 186 : 174} h152 v10 q0 10 -12 10 H56 q-12 0 -12 -10 Z" fill="${MASA_OSC}"/>`;
}

function empanada(o) {
  const col = o.horno === false ? "#EBD7AE" : MASA;
  return `${SOMBRA}
  <path d="M52 156 Q52 78 120 78 Q188 78 188 156 Q188 190 120 190 Q52 190 52 156 Z" fill="${col}"/>
  <path d="M52 156 Q52 190 120 190 Q188 190 188 156 Q160 176 120 176 Q80 176 52 156 Z"
        fill="${MASA_OSC}" opacity=".3"/>
  <g stroke="${MASA_OSC}" stroke-width="5" stroke-linecap="round" opacity=".7" fill="none">
    <path d="M62 172 l14 -12"/><path d="M84 182 l12 -14"/><path d="M110 186 l8 -16"/>
    <path d="M138 184 l6 -16"/><path d="M164 176 l10 -14"/>
  </g>
  <ellipse cx="104" cy="110" rx="34" ry="16" fill="${MASA_LUZ}" opacity=".55"/>
  ${o.queso ? '<path d="M120 132 q-10 20 6 26 q18 -8 6 -26 Z" fill="#F0C86A" opacity=".9"/>' : ""}`;
}

function botella(o) {             /* agua, bebida, jugo, vidrio */
  const liq = o.liq || "#7FC7E8", tapa = o.tapa || "#3E6E8E";
  const vidrio = o.vidrio ? .55 : .28;
  const id = uid();
  const forma = "M96 62 h48 v20 q26 14 26 46 v76 q0 14 -16 14 H86 q-16 0 -16 -14 v-76 q0 -32 26 -46 Z";
  return `${SOMBRA}
  <defs><clipPath id="${id}"><path d="${forma}"/></clipPath></defs>
  <path d="${forma}" fill="#EDF4F6" fill-opacity=".9"/>
  <g clip-path="url(#${id})">
    <rect x="60" y="${o.lleno === false ? 150 : 108}" width="120" height="120" fill="${liq}"/>
    <rect x="60" y="${o.lleno === false ? 150 : 108}" width="120" height="10" fill="#FFFFFF" opacity=".35"/>
  </g>
  <path d="${forma}" fill="none" stroke="#B9CFD8" stroke-width="3.5"/>
  <path d="M104 96 V200" stroke="#FFFFFF" stroke-opacity="${vidrio}" stroke-width="10" stroke-linecap="round"/>
  <rect x="92" y="46" width="56" height="24" rx="7" fill="${tapa}"/>
  <rect x="92" y="46" width="56" height="9" rx="4" fill="#FFFFFF" opacity=".22"/>
  ${o.etiqueta ? `<rect x="70" y="128" width="100" height="42" rx="6" fill="${o.etiqueta}"/>
     <rect x="78" y="140" width="60" height="7" rx="3.5" fill="#FFFFFF" opacity=".75"/>
     <rect x="78" y="153" width="40" height="6" rx="3" fill="#FFFFFF" opacity=".5"/>` : ""}`;
}

function lata(o) {
  const col = o.col2 || o.liq || "#C0304A";
  const id = uid();
  const forma = "M78 74 h84 v112 q0 14 -14 14 H92 q-14 0 -14 -14 Z";
  return `${SOMBRA}
  <defs><clipPath id="${id}"><path d="${forma}"/></clipPath></defs>
  <path d="${forma}" fill="${col}"/>
  <g clip-path="url(#${id})">
    <rect x="78" y="74" width="16" height="130" fill="#FFFFFF" opacity=".22"/>
    <rect x="146" y="74" width="16" height="130" fill="#000000" opacity=".12"/>
    <rect x="78" y="112" width="84" height="34" fill="#FFFFFF" opacity=".85"/>
  </g>
  <ellipse cx="120" cy="74" rx="42" ry="11" fill="#CFD6DA"/>
  <ellipse cx="120" cy="72" rx="36" ry="8" fill="#E6EBEE"/>
  <ellipse cx="120" cy="72" rx="12" ry="4.5" fill="#B6BEC3"/>
  <path d="${forma}" fill="none" stroke="#00000022" stroke-width="2"/>`;
}

function cajaJugo(o) {            /* tetrapak con bombilla */
  const col = o.col2 || o.liq || "#E4913C";
  return `${SOMBRA}
  <path d="M84 78 h72 v112 q0 10 -10 10 H94 q-10 0 -10 -10 Z" fill="${col}"/>
  <path d="M84 78 h72 v112 q0 10 -10 10 h-8 V78 Z" fill="#000000" opacity=".12"/>
  <path d="M84 78 l36 -18 l36 18 Z" fill="${col}" opacity=".8"/>
  <path d="M120 60 l36 18 h-36 Z" fill="#000000" opacity=".1"/>
  <rect x="96" y="112" width="48" height="44" rx="5" fill="#FFFFFF" opacity=".85"/>
  <circle cx="120" cy="130" r="12" fill="${col}" opacity=".55"/>
  <rect x="150" y="24" width="9" height="56" rx="4.5" fill="#D8E5EA" transform="rotate(12 154 52)"/>
  <rect x="139" y="20" width="26" height="9" rx="4.5" fill="#D8E5EA"/>`;
}

function vasoPapel(o) {           /* café para llevar: tapa y manga */
  const manga = o.manga || "#B9825A";
  return `${SOMBRA}
  <path d="M76 84 L88 188 Q90 200 104 200 H136 Q150 200 152 188 L164 84 Z" fill="#F7F2EA"/>
  <path d="M140 84 L164 84 L152 188 Q150 200 136 200 h-8 Z" fill="#E3D8C8" opacity=".7"/>
  <rect x="82" y="116" width="76" height="46" fill="${manga}"/>
  <rect x="82" y="116" width="76" height="12" fill="#FFFFFF" opacity=".18"/>
  <path d="M96 130 h48 M96 144 h34" stroke="#FFFFFF" stroke-opacity=".55"
        stroke-width="5" stroke-linecap="round"/>
  <path d="M68 78 h104 q8 0 8 8 v6 q0 8 -8 8 H68 q-8 0 -8 -8 v-6 q0 -8 8 -8 Z" fill="#6B4A33"/>
  <ellipse cx="120" cy="78" rx="56" ry="10" fill="#7C573D"/>
  <ellipse cx="120" cy="76" rx="48" ry="7" fill="#8A6244"/>
  ${o.hot ? vapor(100, 60, 0) + vapor(140, 56, 1.6) : ""}`;
}

function dona(o) {
  const glas = o.glaseado || "#E7A0C0";
  const id = uid();
  return `${SOMBRA}
  <defs><clipPath id="${id}">
    <path d="M120 68 a62 58 0 1 0 .1 0 Z M120 116 a22 20 0 1 1 -.1 0 Z" clip-rule="evenodd"/>
  </clipPath></defs>
  <ellipse cx="120" cy="140" rx="66" ry="60" fill="${MASA}"/>
  <ellipse cx="120" cy="148" rx="66" ry="52" fill="${MASA_OSC}" opacity=".28"/>
  <path d="M120 80 a62 58 0 1 0 .1 0 Z M120 128 a22 20 0 1 1 -.1 0 Z" fill="${MASA}" clip-rule="evenodd"/>
  <g clip-path="url(#${id})" transform="translate(0 12)">
    <path d="M54 132 q14 -22 32 -8 q16 12 30 -4 q16 -16 32 0 q16 16 34 -2 v-44 h-128 Z" fill="${glas}"/>
    <ellipse cx="120" cy="86" rx="62" ry="26" fill="${glas}"/>
  </g>
  <ellipse cx="120" cy="140" rx="22" ry="20" fill="#F3E3C6"/>
  <ellipse cx="120" cy="140" rx="22" ry="20" fill="${MASA_OSC}" opacity=".35"/>
  ${o.chispas ? `<g>
    <rect x="88" y="106" width="12" height="5" rx="2.5" fill="#C0304A" transform="rotate(-24 94 108)"/>
    <rect x="118" y="98" width="12" height="5" rx="2.5" fill="#3E6E8E" transform="rotate(14 124 100)"/>
    <rect x="148" y="110" width="12" height="5" rx="2.5" fill="#8FB861" transform="rotate(-8 154 112)"/>
    <rect x="102" y="122" width="12" height="5" rx="2.5" fill="#F0C86A" transform="rotate(28 108 124)"/>
    <rect x="136" y="124" width="12" height="5" rx="2.5" fill="#C0304A" transform="rotate(-18 142 126)"/>
   </g>` : ""}`;
}

function muffin(o) {
  const copete = o.copete || "#C08850";
  return `${SOMBRA}
  <path d="M74 132 q46 -58 92 0 q-10 -50 -46 -50 q-36 0 -46 50 Z" fill="${copete}"/>
  <ellipse cx="120" cy="130" rx="50" ry="20" fill="${copete}"/>
  <ellipse cx="104" cy="118" rx="24" ry="11" fill="#FFFFFF" opacity=".22"/>
  ${o.crema ? `<g fill="#FFF7EC">
      <ellipse cx="120" cy="112" rx="34" ry="14"/>
      <circle cx="104" cy="98" r="15"/><circle cx="122" cy="88" r="17"/><circle cx="140" cy="98" r="14"/>
      <path d="M122 62 l8 16 -17 0 Z" fill="#C0304A"/></g>` : ""}
  <path d="M76 130 h88 l-10 56 q-2 12 -14 12 h-40 q-12 0 -14 -12 Z" fill="#C98F63"/>
  <g stroke="#A97544" stroke-width="4" opacity=".55">
    <path d="M92 134 l-6 60"/><path d="M110 134 l-3 62"/>
    <path d="M130 134 l3 62"/><path d="M148 134 l6 60"/>
  </g>
  ${o.chips ? '<g fill="#5A3018"><circle cx="98" cy="116" r="5"/><circle cx="132" cy="110" r="4.6"/><circle cx="146" cy="124" r="4.2"/></g>' : ""}`;
}

function galleta(o) {
  return `${SOMBRA}
  <ellipse cx="120" cy="142" rx="66" ry="62" fill="#E0B270"/>
  <ellipse cx="120" cy="150" rx="66" ry="54" fill="#C08850" opacity=".35"/>
  <ellipse cx="120" cy="136" rx="66" ry="58" fill="#E8BE7E"/>
  <ellipse cx="102" cy="116" rx="30" ry="14" fill="#F3D3A0" opacity=".6"/>
  <g fill="${o.chips === false ? "#C08850" : "#4A2410"}">
    <circle cx="96" cy="126" r="8"/><circle cx="140" cy="118" r="7"/>
    <circle cx="152" cy="150" r="7.5"/><circle cx="104" cy="164" r="7"/>
    <circle cx="126" cy="146" r="6.5"/><circle cx="76" cy="146" r="6"/>
  </g>`;
}

function bol(o) {                 /* sopa, ensalada, yogurt, helado en copa */
  const dentro = o.dentro || "#E8A33C";
  return `${SOMBRA}
  <path d="M46 118 h148 q0 62 -50 74 h-48 q-50 -12 -50 -74 Z" fill="#F7EADB"/>
  <path d="M150 118 h44 q0 62 -50 74 h-26 q42 -18 32 -74 Z" fill="#DFC7AB" opacity=".55"/>
  <ellipse cx="120" cy="118" rx="74" ry="18" fill="#EEDCC6"/>
  <ellipse cx="120" cy="118" rx="64" ry="14" fill="${dentro}"/>
  ${o.granola ? `<g fill="#B9813C">
      <ellipse cx="98" cy="114" rx="9" ry="5" transform="rotate(-18 98 114)"/>
      <ellipse cx="126" cy="120" rx="9" ry="5" transform="rotate(12 126 120)"/>
      <ellipse cx="148" cy="112" rx="8" ry="4.6" transform="rotate(-6 148 112)"/>
      <circle cx="112" cy="122" r="4" fill="#C0304A"/><circle cx="138" cy="124" r="3.6" fill="#C0304A"/>
     </g>` : ""}
  ${o.hojas ? `<g fill="#6E9A4E">
      <ellipse cx="96" cy="112" rx="20" ry="11" transform="rotate(-22 96 112)"/>
      <ellipse cx="132" cy="116" rx="22" ry="12" transform="rotate(16 132 116)"/>
      <ellipse cx="152" cy="110" rx="16" ry="9" transform="rotate(-10 152 110)" fill="#8FB861"/>
      <circle cx="112" cy="120" r="7" fill="#C0304A"/>
     </g>` : ""}
  ${o.hot ? vapor(100, 100, 0) + vapor(140, 96, 1.7) : ""}`;
}

function helado(o) {              /* cono */
  const bola = o.bola || "#F3D3A0", bola2 = o.bola2 || "#C0304A";
  return `${SOMBRA}
  <path d="M92 128 L120 202 L148 128 Z" fill="#E0B270"/>
  <g stroke="#C08850" stroke-width="3" opacity=".6">
    <path d="M100 140 l32 22"/><path d="M110 162 l24 16"/><path d="M136 140 l-30 22"/>
  </g>
  <circle cx="106" cy="116" r="28" fill="${bola}"/>
  <circle cx="140" cy="112" r="26" fill="${bola2}"/>
  <circle cx="122" cy="90" r="24" fill="${o.bola3 || "#FFF7EC"}"/>
  <circle cx="114" cy="82" r="8" fill="#FFFFFF" opacity=".45"/>`;
}

function tetera(o) {
  const col = o.col2 || "#B96A4A";
  return `${SOMBRA}
  <path d="M172 122 c34 -4 38 44 4 48" fill="none" stroke="${col}" stroke-width="15" stroke-linecap="round"/>
  <path d="M62 130 q-26 -6 -30 12 q-3 14 14 18" fill="none" stroke="${col}"
        stroke-width="13" stroke-linecap="round"/>
  <ellipse cx="118" cy="150" rx="62" ry="48" fill="${col}"/>
  <ellipse cx="118" cy="158" rx="62" ry="40" fill="#000000" opacity=".12"/>
  <ellipse cx="100" cy="128" rx="30" ry="14" fill="#FFFFFF" opacity=".22"/>
  <ellipse cx="118" cy="104" rx="30" ry="10" fill="${col}"/>
  <ellipse cx="118" cy="100" rx="22" ry="8" fill="#000000" opacity=".15"/>
  <circle cx="118" cy="94" r="8" fill="${col}"/>
  ${o.hot ? vapor(150, 84, 0) + vapor(178, 92, 1.4) : ""}`;
}

function porcion(o) {             /* pizza o tarta, vista en triángulo */
  const base = o.base || "#E8BE7E", cubierta = o.cubierta || "#C0304A";
  return `${SOMBRA}
  <path d="M120 62 L196 186 H44 Z" fill="${base}"/>
  <path d="M120 62 L196 186 H120 Z" fill="#000000" opacity=".08"/>
  <path d="M44 186 H196 q-8 16 -22 16 H66 q-14 0 -22 -16 Z" fill="${MASA}"/>
  <path d="M120 84 L182 178 H58 Z" fill="${cubierta}" opacity=".9"/>
  ${o.pepperoni ? `<g fill="#8E1F2B">
      <circle cx="120" cy="120" r="12"/><circle cx="96" cy="152" r="11"/>
      <circle cx="146" cy="150" r="11"/><circle cx="120" cy="168" r="9"/></g>` : ""}
  ${o.queso ? `<g fill="#F6DFA6" opacity=".85">
      <ellipse cx="108" cy="112" rx="14" ry="8"/><ellipse cx="140" cy="140" rx="16" ry="9"/>
      <ellipse cx="98" cy="158" rx="13" ry="7"/></g>` : ""}`;
}

function plato(o) {               /* lo que no calza en nada: plato con algo */
  const col = o.col2 || "#C08850";
  return `${SOMBRA}
  <ellipse cx="120" cy="176" rx="88" ry="20" fill="#E4D2BB"/>
  <ellipse cx="120" cy="170" rx="88" ry="20" fill="#F7EADB"/>
  <ellipse cx="120" cy="168" rx="60" ry="13" fill="#EEDCC6"/>
  <ellipse cx="120" cy="148" rx="50" ry="26" fill="${col}"/>
  <ellipse cx="120" cy="142" rx="50" ry="24" fill="${col}"/>
  <ellipse cx="104" cy="134" rx="22" ry="9" fill="#FFFFFF" opacity=".22"/>
  ${o.hojas ? '<g fill="#6E9A4E"><ellipse cx="150" cy="140" rx="18" ry="9" transform="rotate(18 150 140)"/><ellipse cx="92" cy="146" rx="15" ry="8" transform="rotate(-14 92 146)"/></g>' : ""}
  ${o.hot ? vapor(102, 118, 0) + vapor(140, 114, 1.5) : ""}`;
}

function combo(o) {               /* dos cosas juntas: promo, desayuno */
  return `${SOMBRA}
  <g transform="translate(-34 14) scale(.72)">
    <path d="M76 84 L88 188 Q90 200 104 200 H136 Q150 200 152 188 L164 84 Z" fill="#F7EADB"/>
    <path d="M140 84 L164 84 L152 188 Q150 200 136 200 h-8 Z" fill="#DFC7AB" opacity=".6"/>
    <ellipse cx="120" cy="84" rx="44" ry="11" fill="#EEDCC6"/>
    <ellipse cx="120" cy="85" rx="37" ry="8.6" fill="${o.liq || "#3A1B0C"}"/>
  </g>
  <g transform="translate(56 34) scale(.62)">
    <path d="M52 156 Q52 78 120 78 Q188 78 188 156 Q188 190 120 190 Q52 190 52 156 Z" fill="${MASA}"/>
    <g stroke="${MASA_OSC}" stroke-width="6" stroke-linecap="round" opacity=".7" fill="none">
      <path d="M70 174 l14 -12"/><path d="M100 184 l10 -14"/><path d="M136 182 l8 -16"/>
      <path d="M164 172 l10 -14"/>
    </g>
    <ellipse cx="104" cy="110" rx="34" ry="16" fill="${MASA_LUZ}" opacity=".55"/>
  </g>`;
}

function pack(o) {                /* el six-pack: la unidad de venta de una botilleria */
  const col = o.col2 || o.liq || "#B8862B";
  const carton = o.carton || "#8A5A34";
  const cuellos = [88, 120, 152].map((x) => `
    <rect x="${x - 9}" y="62" width="18" height="34" rx="4" fill="${col}"/>
    <rect x="${x - 11}" y="56" width="22" height="12" rx="4" fill="#C9A227"/>`).join("");
  return `${SOMBRA}
  ${cuellos}
  <path d="M62 92 h116 v96 q0 12 -12 12 H74 q-12 0 -12 -12 Z" fill="${carton}"/>
  <path d="M62 92 h116 v20 H62 Z" fill="#FFFFFF" opacity=".14"/>
  <path d="M166 92 h12 v96 q0 12 -12 12 h-8 Z" fill="#000000" opacity=".13"/>
  <rect x="80" y="122" width="80" height="42" rx="6" fill="#FFFFFF" opacity=".85"/>
  <rect x="90" y="134" width="52" height="8" rx="4" fill="${col}" opacity=".75"/>
  <rect x="90" y="148" width="34" height="7" rx="3.5" fill="${col}" opacity=".5"/>
  <path d="M96 92 q24 -22 48 0" fill="none" stroke="#000000" stroke-opacity=".18" stroke-width="4"/>`;
}

function bolsa(o) {              /* bolsa de café stand-up: válvula y etiqueta en blanco, sin marca */
  const id = uid();
  const base = hexOk(o.col, o.kraft ? "#B98B5E" : "#2E5E4E");
  const sombra = oscuro(base, .28), luz = claro(base, .22), borde = oscuro(base, .38);
  const cuerpo = "M64 70 L55 176 Q53 196 76 199 Q120 205 164 199 Q187 196 185 176 L176 70 Z";
  return `${SOMBRA}
  <defs><linearGradient id="${id}" x1="0" x2="1" y1="0" y2="0">
    <stop offset="0" stop-color="${luz}"/><stop offset=".22" stop-color="${base}"/>
    <stop offset=".72" stop-color="${base}"/><stop offset="1" stop-color="${sombra}"/>
  </linearGradient></defs>
  <path d="${cuerpo}" fill="url(#${id})" stroke="${borde}" stroke-width="2" stroke-linejoin="round"/>
  <path d="M55 176 Q53 196 76 199 Q120 205 164 199 Q187 196 185 176 Q120 188 55 176 Z" fill="${sombra}" opacity=".5"/>
  <path d="M62 52 H178 V72 H62 Z" fill="${claro(base, .1)}" stroke="${borde}" stroke-width="2" stroke-linejoin="round"/>
  <path d="M62 58 H178 M62 64 H178" stroke="${borde}" stroke-width="1.8" opacity=".45"/>
  <path d="M66 86 H174" stroke="${borde}" stroke-width="2" stroke-dasharray="3 3" opacity=".5"/>
  <circle cx="120" cy="104" r="11" fill="${oscuro(base, .45)}"/>
  <circle cx="120" cy="104" r="8" fill="${claro(base, .55)}"/>
  <circle cx="120" cy="104" r="3.4" fill="${oscuro(base, .5)}"/>
  <rect x="80" y="124" width="80" height="54" rx="7" fill="#F7EFDE" stroke="${borde}" stroke-opacity=".35" stroke-width="2"/>
  <rect x="86" y="130" width="68" height="42" rx="4" fill="none" stroke="#C9B58F" stroke-width="1.6" opacity=".7"/>
  <path d="M70 80 L63 176" stroke="#FFFFFF" stroke-opacity=".28" stroke-width="7" stroke-linecap="round"/>
  ${o.kraft ? `<g stroke="${borde}" stroke-width="1.6" opacity=".28" stroke-linecap="round">
    <path d="M72 100 l8 3 M160 96 l9 -3 M70 140 l7 2 M164 150 l8 3 M76 184 l9 1 M150 188 l10 1"/></g>` : ""}`;
}

function bolsaPapel(o) {         /* bolsa de papel de panadería, con las puntas de dos baguettes */
  const base = hexOk(o.col, "#C9A06A");
  const sombra = oscuro(base, .24), luz = claro(base, .25), borde = oscuro(base, .38);
  return `${SOMBRA}
  <g transform="rotate(-9 96 80)">
    <rect x="76" y="44" width="30" height="62" rx="15" fill="${MASA}"/>
    <path d="M82 66 l12 -6 M82 80 l12 -6" stroke="${MASA_OSC}" stroke-width="4" stroke-linecap="round" opacity=".7"/>
  </g>
  <g transform="rotate(10 150 80)">
    <rect x="134" y="48" width="30" height="58" rx="15" fill="#E6B567"/>
    <path d="M140 70 l12 -6 M140 84 l12 -6" stroke="${MASA_OSC}" stroke-width="4" stroke-linecap="round" opacity=".7"/>
  </g>
  <path d="M62 96 H178 L186 190 Q186 200 174 200 H66 Q54 200 54 190 Z" fill="${base}" stroke="${borde}" stroke-width="2" stroke-linejoin="round"/>
  <path d="M142 96 H178 L186 190 Q186 200 174 200 H150 Z" fill="${sombra}" opacity=".5"/>
  <path d="M60 84 H180 L178 108 H62 Z" fill="${luz}" stroke="${borde}" stroke-width="2" stroke-linejoin="round"/>
  <path d="M120 108 V200" stroke="${borde}" stroke-width="2" opacity=".28"/>
  <rect x="82" y="128" width="76" height="46" rx="6" fill="#F7EFDE" stroke="${borde}" stroke-opacity=".35" stroke-width="2"/>
  <path d="M68 112 L62 194" stroke="#FFFFFF" stroke-opacity=".25" stroke-width="6" stroke-linecap="round"/>`;
}

const ART = { mug, taza, vaso, frappe, croissant, torta, brownie, alfajor,
              pan, sandwich, empanada, botella, lata, cajaJugo, vasoPapel,
              dona, muffin, galleta, bol, helado, tetera, porcion, plato,
              combo, pack, bolsa, bolsaPapel };
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

  /* ---------- panadería y masas ---------- */
  "pan":                 { k: "pan", tipo: "marraqueta" },
  "pan-marraqueta":      { k: "pan", tipo: "marraqueta" },
  "pan-hallulla":        { k: "pan", tipo: "hallulla" },
  "pan-amasado":         { k: "pan", tipo: "amasado" },
  "pan-baguette":        { k: "pan", tipo: "baguette" },
  "pan-integral":        { k: "pan", tipo: "integral" },
  "pan-ciabatta":        { k: "pan", tipo: "ciabatta" },
  "pan-frica":           { k: "pan", tipo: "frica" },
  "sandwich":            { k: "sandwich", relleno: "#C0304A" },
  "sandwich-queso":      { k: "sandwich", relleno: "#E0A15A", queso: 1 },
  "churrasco":           { k: "sandwich", relleno: "#8E5A3C", queso: 1 },
  "wrap":                { k: "sandwich", tipo: "wrap" },
  "empanada":            { k: "empanada" },
  "empanada-queso":      { k: "empanada", queso: 1 },
  "empanada-cruda":      { k: "empanada", horno: false },

  /* ---------- dulces ---------- */
  "dona":                { k: "dona", glaseado: "#E7A0C0" },
  "dona-chocolate":      { k: "dona", glaseado: "#5A3018" },
  "dona-chispas":        { k: "dona", glaseado: "#E7A0C0", chispas: 1 },
  "muffin":              { k: "muffin" },
  "muffin-chips":        { k: "muffin", chips: 1 },
  "cupcake":             { k: "muffin", crema: 1 },
  "galleta":             { k: "galleta" },
  "galleta-avena":       { k: "galleta", chips: false },
  "helado":              { k: "helado" },
  "helado-chocolate":    { k: "helado", bola: "#5A3018", bola2: "#C08850", bola3: "#F3D3A0" },
  "torta-chocolate":     { k: "torta", glaseado: "#5A3018", relleno: "#7A4A28" },
  "torta-limon":         { k: "torta", glaseado: "#E8D45A", relleno: "#FBF1E0" },
  "cheesecake":          { k: "torta", glaseado: "#C0304A", relleno: "#FFF7EC" },
  "kuchen":              { k: "porcion", base: "#E8BE7E", cubierta: "#B8452F" },
  "pie-limon":           { k: "porcion", base: "#E8BE7E", cubierta: "#F3E08A" },

  /* ---------- envases y bebidas frías ---------- */
  "botella-agua":        { k: "botella", liq: "#9FD8F0", tapa: "#3E6E8E" },
  "botella-bebida":      { k: "botella", liq: "#7A3B24", tapa: "#C0304A", etiqueta: "#C0304A" },
  "botella-jugo":        { k: "botella", liq: "#E8A33C", tapa: "#B5892E", etiqueta: "#E8A33C" },
  "botella-vidrio":      { k: "botella", liq: "#8FB861", tapa: "#4E7C5B", vidrio: 1 },
  "lata":                { k: "lata", liq: "#C0304A" },
  "lata-verde":          { k: "lata", liq: "#4E7C5B" },
  "lata-naranja":        { k: "lata", liq: "#E4913C" },
  "jugo-caja":           { k: "cajaJugo", liq: "#E4913C" },
  "jugo-caja-verde":     { k: "cajaJugo", liq: "#8FB861" },

  /* ---------- para llevar y calientes ---------- */
  "para-llevar":         { k: "vasoPapel", manga: "#B9825A", hot: 1 },
  "para-llevar-te":      { k: "vasoPapel", manga: "#6E9A4E", hot: 1 },
  "para-llevar-frio":    { k: "vasoPapel", manga: "#3E6E8E" },
  "tetera":              { k: "tetera", col2: "#B96A4A", hot: 1 },
  "tetera-verde":        { k: "tetera", col2: "#4E7C5B", hot: 1 },

  /* ---------- comida ---------- */
  "sopa":                { k: "bol", dentro: "#E8A33C", hot: 1 },
  "ensalada":            { k: "bol", dentro: "#F1E7D4", hojas: 1 },
  "yogurt":              { k: "bol", dentro: "#FFF7EC", granola: 1 },
  "pizza":               { k: "porcion", cubierta: "#C0304A", pepperoni: 1, queso: 1 },
  "plato":               { k: "plato", col2: "#C08850", hot: 1 },
  "plato-frio":          { k: "plato", col2: "#E8BE7E", hojas: 1 },
  "combo":               { k: "combo", liq: "#3A1B0C" },
  "desayuno":            { k: "combo", liq: "#6B4022" },
  /* ---- botillería y almacén ----
     Lo que de verdad se vende en un local de barrio: cervezas, bebidas, vinos
     y destilados. Se arman con las mismas piezas cambiándoles el color, que es
     todo lo que hace falta para reconocerlas de un vistazo en la grilla. */
  "cerveza-lata":        { k: "lata", col2: "#C8A02E" },
  "cerveza-lata-roja":   { k: "lata", col2: "#B5232E" },
  "cerveza-lata-verde":  { k: "lata", col2: "#2E7D4F" },
  "cerveza-lata-azul":   { k: "lata", col2: "#2C5C93" },
  "cerveza-botella":     { k: "botella", liq: "#B8791E", tapa: "#8A5A34", vidrio: 1, etiqueta: "#C8A02E" },
  "cerveza-botella-verde": { k: "botella", liq: "#4F7A34", tapa: "#2E7D4F", vidrio: 1, etiqueta: "#2E7D4F" },
  "cerveza-litro":       { k: "botella", liq: "#9C6318", tapa: "#6B4423", vidrio: 1, etiqueta: "#8A5A34" },
  "pack-cervezas":       { k: "pack", col2: "#C8A02E", carton: "#8A5A34" },
  "pack-bebidas":        { k: "pack", col2: "#B5232E", carton: "#3E6E8E" },

  "bebida-cola":         { k: "botella", liq: "#2A1208", tapa: "#B5232E", etiqueta: "#B5232E" },
  "bebida-naranja":      { k: "botella", liq: "#E4913C", tapa: "#D9761F", etiqueta: "#D9761F" },
  "bebida-amarilla":     { k: "botella", liq: "#E8C33C", tapa: "#C9A227", etiqueta: "#C9A227" },
  "bebida-lima":         { k: "botella", liq: "#7FB93C", tapa: "#4F7A34", etiqueta: "#4F7A34" },
  "bebida-lata-cola":    { k: "lata", col2: "#B5232E" },
  "bebida-lata-naranja": { k: "lata", col2: "#D9761F" },
  "agua-mineral":        { k: "botella", liq: "#9CD0D6", tapa: "#3E6E8E", etiqueta: "#3E6E8E" },
  "agua-con-gas":        { k: "botella", liq: "#BFE3EC", tapa: "#2E7D4F", etiqueta: "#2E7D4F" },
  "energetica":          { k: "lata", col2: "#3E6E8E" },

  "vino-tinto":          { k: "botella", liq: "#5A1226", tapa: "#3A0C18", vidrio: 1, etiqueta: "#7A1B33" },
  "vino-blanco":         { k: "botella", liq: "#E3D79A", tapa: "#C9A227", vidrio: 1, etiqueta: "#C9A227" },
  "espumante":           { k: "botella", liq: "#EBD9A0", tapa: "#C9A227", vidrio: 1, etiqueta: "#8A6A22" },
  "pisco":               { k: "botella", liq: "#F0E4C4", tapa: "#8A5A34", vidrio: 1, etiqueta: "#A9762E" },
  "ron":                 { k: "botella", liq: "#7A3E14", tapa: "#3A1B0C", vidrio: 1, etiqueta: "#5A2A0E" },
  "whisky":              { k: "botella", liq: "#A5601A", tapa: "#3A1B0C", vidrio: 1, etiqueta: "#6B4423" },

  /* ---- bolsas: el color se elige en la ficha del producto (col) ---- */
  "bolsa-cafe":          { k: "bolsa", col: "#2E5E4E" },
  "bolsa-cafe-roja":     { k: "bolsa", col: "#A8382F" },
  "bolsa-cafe-azul":     { k: "bolsa", col: "#2F5D8A" },
  "bolsa-cafe-negra":    { k: "bolsa", col: "#2B2523" },
  "bolsa-cafe-kraft":    { k: "bolsa", kraft: 1 },
  "bolsa-papel":         { k: "bolsaPapel", col: "#C9A06A" },
  "bolsa-papel-blanca":  { k: "bolsaPapel", col: "#F1EBDD" },

  "leche-caja":          { k: "cajaJugo", col2: "#3E6E8E" },
  "nectar-caja":         { k: "cajaJugo", col2: "#C0392B" },

};

/* En la caja el vapor y las burbujas van quietos: sin animación. */
const dibujo = (a) => {
  const receta = RECETAS[(a && a.k) || "mug"] || RECETAS.mug;
  const art = Object.assign({}, receta);
  if (a && a.col) art.col = a.col;          // el color elegido manda sobre la receta
  if (a && a.kraft) { art.kraft = 1; if (!(a && a.col)) delete art.col; }   // bolsa de papel café
  // Recorte: el lienzo de 240 tiene mucho aire arriba y a los lados, y en un
  // azulejo chico eso hace que el dibujo se vea perdido. Mostramos solo la parte
  // donde realmente hay algo dibujado.
  return `<svg class="art" viewBox="22 38 196 182" preserveAspectRatio="xMidYMid meet" aria-hidden="true">${(ART[art.k] || mug)(art)}</svg>`;
};

// Lo único que sale: la caja y la pantalla llaman `dibujo(...)` a secas.
window.dibujo = dibujo;
})();
