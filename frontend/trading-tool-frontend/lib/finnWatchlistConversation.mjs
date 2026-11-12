const WATCHLIST = /\b(?:watchlist|wachtlist|wachtlijst|volglijst|marktenlijst|volgen|volg)\b/i;
const ADD = /\b(?:voeg|toevoegen|toegevoegd|add|follow|volg)\b/i;
const REMOVE = /\b(?:verwijder|haal|stop|remove|unfollow)\b|niet\s+meer\s+volgen/i;
const REPLACE = /\b(?:vervang|vervangen|replace|instead of)\b|in\s+plaats\s+van|niet\s+meer(?:\s+\w+){0,3}\s+volgen/i;

function directedReplacement(value, assets) {
  if (new Set(assets.map((asset) => asset.symbol)).size !== 2) return null;
  const direction = (fragment, pair) => {
    const [first, second] = pair;
    const marker = /\b(?:in\s+plaats\s+van|instead\s+of|anstatt)\b/i.exec(fragment);
    if (marker && first.end <= marker.index && second.start >= marker.index + marker[0].length) return [second, first];
    if (marker && marker.index + marker[0].length <= first.start) return [first, second];
    if (/\b(?:vervang|replace|ersetze)\b/i.test(fragment) && /\b(?:door|with|durch)\b/i.test(fragment)) {
      return /\b(?:niet|not|nicht)\b/i.test(fragment) ? null : [first, second];
    }
    if ((REMOVE.test(fragment) && ADD.test(fragment)) || /niet\s+meer\s+volgen.*\b(?:volg|follow)\b/i.test(fragment)) {
      return [first, second];
    }
    return null;
  };

  const directions = [];
  let extraCommand = false;
  for (const sentence of value.matchAll(/[^.;!?]+/g)) {
    const starts = [0];
    for (const command of sentence[0].matchAll(/\b(?:vervang|replace|ersetze)\b/gi)) {
      if (command.index > 0) starts.push(command.index);
    }
    starts.push(sentence[0].length);
    for (let index = 0; index < starts.length - 1; index += 1) {
      const from = sentence.index + starts[index];
      const to = sentence.index + starts[index + 1];
      const fragment = value.slice(from, to);
      const pair = assets.filter((asset) => asset.start >= from && asset.end <= to)
        .map((asset) => ({ ...asset, start: asset.start - from, end: asset.end - from }));
      if (pair.length > 2) return { issue: 'conflict' };
      if (pair.length === 2 && pair[0].symbol === pair[1].symbol && /\b(?:vervang|replace|ersetze)\b/i.test(fragment)) return { issue: 'conflict' };
      if (pair.length === 2 && /\b(?:vervang|replace|ersetze)\b/i.test(fragment) && /\b(?:niet|not|nicht)\b/i.test(fragment)) return { issue: 'negated' };
      if (pair.length === 2 && pair[0].symbol !== pair[1].symbol) {
        const parsed = direction(fragment, pair);
        if (parsed) directions.push(parsed);
        else if (ADD.test(fragment) || REMOVE.test(fragment) || REPLACE.test(fragment)) extraCommand = true;
      } else if (pair.length === 1 && (ADD.test(fragment) || REMOVE.test(fragment) || REPLACE.test(fragment))) {
        extraCommand = true;
      }
    }
  }
  const hasDirectedClause = directions.length > 0;
  if (!directions.length && assets.length === 2) {
    const parsed = direction(value, assets);
    if (parsed) directions.push(parsed);
  }
  if (!directions.length) return null;
  if (hasDirectedClause && extraCommand) return { issue: 'conflict' };
  const [source, target] = directions[0].map((asset) => ({ ...asset }));
  for (const [nextSource, nextTarget] of directions.slice(1)) {
    if (source.symbol !== nextSource.symbol || target.symbol !== nextTarget.symbol) return { issue: 'conflict' };
    for (const [current, next] of [[source, nextSource], [target, nextTarget]]) {
      if (next.quote_currency) {
        if (current.quote_currency && current.quote_currency !== next.quote_currency) return { issue: 'conflict' };
        current.quote_currency = next.quote_currency;
      }
    }
  }
  return { source, target };
}

const COPY = {
  nl: { scope: 'Bedoel je je watchlist of je portfolio?', watchlist: 'Watchlist', portfolio: 'Portfolio',
    scopeAction: 'Wat wil je in je watchlist doen?',
    addReply: (name) => `Voeg ${name} toe aan mijn watchlist`, portfolioReply: (name) => `Ik bedoel mijn portfolio met ${name}`,
    assets: 'Welke asset wil je toevoegen en welke wil je niet meer volgen?', conflict: 'Je noemt meerdere wijzigingen of noteringen in één verzoek. Welke wijziging wil je eerst in je watchlist doen?', negated: 'Begrepen, ik voer deze vervanging niet uit.', source: (name) => `${name} staat niet in je watchlist. Welke bestaande asset wil je vervangen?`,
    missing: 'Die asset staat niet in je watchlist. Welke wil je verwijderen?', unavailable: (name) => `Ik kan nu geen handelspaar voor ${name} verifiëren. Probeer het later opnieuw.`,
    pairUnavailable: (pair) => `${pair} is niet beschikbaar. Welk handelspaar bedoel je?`, replace: 'Kies de nieuwe notering. Je bevestigt daarna eerst de toevoeging en vervolgens het verwijderen van de oude notering.',
    remove: 'Welke notering wil je verwijderen?', choose: (name) => `Welke notering van ${name} wil je volgen?`, add: 'Wil je deze asset aan je watchlist toevoegen?',
    replaceLabel: (source, target) => `${source} vervangen door ${target}`, removeLabel: (source) => `${source} verwijderen`, addLabel: (target) => `${target} toevoegen` },
  en: { scope: 'Do you mean your watchlist or your portfolio?', watchlist: 'Watchlist', portfolio: 'Portfolio',
    scopeAction: 'What would you like to do in your watchlist?',
    addReply: (name) => `Add ${name} to my watchlist`, portfolioReply: (name) => `I mean my portfolio with ${name}`,
    assets: 'Which asset would you like to add, and which should you stop following?', conflict: 'You mentioned several changes or listings in one request. Which watchlist change would you like to make first?', negated: 'Understood. I will not make this replacement.', source: (name) => `${name} is not in your watchlist. Which existing asset should I replace?`,
    missing: 'That asset is not in your watchlist. Which one should I remove?', unavailable: (name) => `I cannot verify a trading pair for ${name} right now. Please try again later.`,
    pairUnavailable: (pair) => `${pair} is unavailable. Which trading pair do you mean?`, replace: 'Choose the new listing. You will confirm its addition first, then removal of the old listing.',
    remove: 'Which listing should I remove?', choose: (name) => `Which ${name} listing would you like to follow?`, add: 'Do you want to add this asset to your watchlist?',
    replaceLabel: (source, target) => `Replace ${source} with ${target}`, removeLabel: (source) => `Remove ${source}`, addLabel: (target) => `Add ${target}` },
  de: { scope: 'Meinst du deine Watchlist oder dein Portfolio?', watchlist: 'Watchlist', portfolio: 'Portfolio',
    scopeAction: 'Was möchtest du in deiner Watchlist tun?',
    addReply: (name) => `Füge ${name} meiner Watchlist hinzu`, portfolioReply: (name) => `Ich meine mein Portfolio mit ${name}`,
    assets: 'Welchen Wert möchtest du hinzufügen und welchen nicht mehr verfolgen?', conflict: 'Du nennst mehrere Änderungen oder Notierungen in einer Anfrage. Welche Änderung möchtest du zuerst an deiner Watchlist vornehmen?', negated: 'Verstanden. Ich nehme diesen Austausch nicht vor.', source: (name) => `${name} ist nicht in deiner Watchlist. Welchen vorhandenen Wert möchtest du ersetzen?`,
    missing: 'Dieser Wert ist nicht in deiner Watchlist. Welchen möchtest du entfernen?', unavailable: (name) => `Ich kann derzeit kein Handelspaar für ${name} verifizieren. Versuche es später erneut.`,
    pairUnavailable: (pair) => `${pair} ist nicht verfügbar. Welches Handelspaar meinst du?`, replace: 'Wähle die neue Notierung. Du bestätigst zuerst das Hinzufügen und danach das Entfernen der alten Notierung.',
    remove: 'Welche Notierung möchtest du entfernen?', choose: (name) => `Welche Notierung von ${name} möchtest du verfolgen?`, add: 'Möchtest du diesen Wert zur Watchlist hinzufügen?',
    replaceLabel: (source, target) => `${source} durch ${target} ersetzen`, removeLabel: (source) => `${source} entfernen`, addLabel: (target) => `${target} hinzufügen` },
};

export function watchlistIntent(text, mentions, ownedRows = []) {
  const value = String(text || '');
  const assets = Array.isArray(mentions) ? mentions : [];
  const hasAdd = ADD.test(value);
  const hasRemove = REMOVE.test(value);
  if (!WATCHLIST.test(value)) {
    if (assets.length === 2 && hasAdd && hasRemove) {
      const addAt = value.search(ADD);
      const removeAt = value.search(REMOVE);
      return { kind: 'clarify_scope', target: addAt < removeAt ? assets[0] : assets[1] };
    }
    if (assets.length && /\b(?:aandeel|asset)\b.*\b(?:aanpassen|wijzigen|veranderen)\b.*\b(?:in|naar)\b/i.test(value)) {
      return { kind: 'clarify_scope', target: assets.at(-1) };
    }
    return null;
  }
  const replacing = REPLACE.test(value) || (hasAdd && hasRemove);
  if (!hasAdd && !hasRemove && !replacing) return null;
  if (replacing) {
    const replacement = directedReplacement(value, assets);
    if (!replacement) return { kind: 'clarify_assets' };
    if (replacement.issue) return { kind: replacement.issue === 'negated' ? 'acknowledge_no_action' : 'clarify_conflict' };
    const { source, target } = replacement;
    if (!ownedRows.some((row) => row.symbol === source.symbol)) return { kind: 'source_missing', source };
    return { kind: 'replace', source, target };
  }
  if (assets.length !== 1) return { kind: 'clarify_assets' };
  return { kind: hasRemove ? 'remove' : 'add', target: assets[0] };
}

export function watchlistChoices(intent, ownedRows, markets = [], locale = 'nl') {
  if (!intent) return null;
  const copy = COPY[String(locale || 'nl').split('-')[0]] || COPY.nl;
  if (intent.kind === 'clarify_scope') {
    return { question: copy.scope, choices: [
      { label: copy.watchlist, action: { kind: 'clarify_watchlist_scope', target: intent.target } },
      { label: copy.portfolio, reply: copy.portfolioReply(intent.target.display_name) },
    ] };
  }
  if (intent.kind === 'clarify_assets') return { question: copy.assets, choices: [] };
  if (intent.kind === 'clarify_conflict') return { question: copy.conflict, choices: [] };
  if (intent.kind === 'acknowledge_no_action') return { question: copy.negated, choices: [] };
  if (intent.kind === 'source_missing') return { question: copy.source(intent.source.display_name), choices: [] };
  const sourceRows = intent.kind === 'replace' || intent.kind === 'remove'
    ? ownedRows.filter((row) => row.symbol === (intent.source || intent.target).symbol &&
        (!(intent.source || intent.target).quote_currency ||
          row.quote_currency === (intent.source || intent.target).quote_currency))
    : [null];
  if (!sourceRows.length) return { question: copy.missing, choices: [] };
  const target = intent.target;
  const targets = intent.kind === 'remove' ? [null]
    : target.asset_class === 'crypto'
      ? markets.filter((market) => market.status !== 'unavailable' &&
          (!target.quote_currency || target.quote_currency === market.quote_currency))
      : [null];
  if (!targets.length) return { question: target.quote_currency
    ? copy.pairUnavailable(`${target.symbol}/${target.quote_currency}`)
    : copy.unavailable(target.display_name), choices: [] };
  const choices = sourceRows.flatMap((sourceRow) => targets.map((market) => {
    const pair = market ? `${target.symbol}/${market.quote_currency}` : target.display_name;
    const sourceLabel = sourceRow?.quote_currency ? `${sourceRow.symbol}/${sourceRow.quote_currency}` : sourceRow?.symbol;
    const label = intent.kind === 'replace' ? copy.replaceLabel(sourceLabel, pair)
      : intent.kind === 'remove' ? copy.removeLabel(sourceLabel) : copy.addLabel(pair);
    return { label, action: { kind: intent.kind, source_symbol: sourceRow?.symbol || null,
      source_market_id: sourceRow?.market_id ?? null,
      source_quote_currency: sourceRow?.quote_currency || null,
      source_asset_class: (intent.source || intent.target)?.asset_class || null,
      source_is_legacy: Boolean(sourceRow && sourceRow.market_id == null),
      target_symbol: target.symbol,
      target_quote_currency: market?.quote_currency || null } };
  }));
  return { question: intent.kind === 'replace' ? copy.replace
    : intent.kind === 'remove' ? copy.remove
    : targets.length > 1 ? copy.choose(target.display_name)
      : copy.add, choices };
}

export function watchlistScopeChoices(target, ownedRows, markets = [], locale = 'nl') {
  const copy = COPY[String(locale || 'nl').split('-')[0]] || COPY.nl;
  const add = watchlistChoices({ kind: 'add', target }, ownedRows, markets, locale);
  const replacements = ownedRows.filter((row) => row.symbol !== target.symbol).flatMap((row) =>
    watchlistChoices({ kind: 'replace', source: row, target }, ownedRows, markets, locale)?.choices
      .filter((choice) => choice.action.source_market_id === (row.market_id ?? null)) || []);
  return { question: copy.scopeAction, choices: [...add.choices, ...replacements] };
}

export function replacementAfterConfirmedAdd(pending, operationId, confirmed) {
  if (!pending || operationId !== 'watchlist_add') return null;
  if (String(confirmed?.asset || '').toUpperCase() !== pending.target_symbol ||
      String(confirmed?.quote_currency || '').toUpperCase() !== String(pending.target_quote_currency || '').toUpperCase()) {
    return null;
  }
  return {
    sourceLabel: pending.source_quote_currency
      ? `${pending.source_symbol}/${pending.source_quote_currency}` : pending.source_symbol,
    action: { ...pending, kind: 'remove' },
  };
}
