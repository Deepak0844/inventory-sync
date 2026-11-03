/** Small HTML pages used by the selector tests. */
export function page(body: string): Document {
  return new DOMParser().parseFromString(`<!doctype html><html><head></head><body>${body}</body></html>`, "text/html");
}

export const PRODUCT = `
<header><nav class="nav"><a href="/" class="nav-link">Home</a><a href="/cart" class="nav-link">Cart</a></nav></header>
<main>
  <h1 id="title">Trail Shoe</h1>
  <p class="stock-status">Out of stock</p>
  <span class="qty-left">Only 3 left</span>
  <form>
    <input name="email" type="text">
    <button data-testid="add-to-cart" class="css-1x2y3z">Add to cart</button>
    <button aria-label="Open size guide" class="btn">?</button>
  </form>
  <ul class="sizes"><li class="size">S</li><li class="size">M</li><li class="size">L</li></ul>
</main>`;

export const DUPLICATES = `
<section id="a"><h2>Left</h2><button class="buy">Buy</button></section>
<section id="b"><h2>Right</h2><button class="buy">Buy</button></section>`;

export const GENERATED = `
<div id=":r1:" class="css-1x2y3z sc-abc123"><span class="price">$5</span></div>
<div id="radix-:r3:"><span>Deep</span></div>
<div class="Button_primary__a1B2c"><i>icon</i></div>`;

export const UTILITY = `
<div class="flex mt-4 px-2"><p class="text-sm font-medium">One</p></div>
<div class="flex mt-4 px-2"><p class="text-sm font-medium">Two</p></div>`;
