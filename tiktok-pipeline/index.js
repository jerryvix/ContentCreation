// ============================================================
// @chatjerrpt TikTok Daily Content Pipeline
// Scrapes YouTube + Twitter + Instagram, scores with Claude,
// drafts 3 post packages, emails them every morning at 7 AM.
// ============================================================

require('dotenv').config();
const { ApifyClient } = require('apify-client');
const Anthropic = require('@anthropic-ai/sdk');
const cron = require('node-cron');
const nodemailer = require('nodemailer');

// ----- Credentials -----
const {
  APIFY_TOKEN,
  ANTHROPIC_KEY,
  EMAIL_TO,
  TWITTER_COOKIE,
  GMAIL_USER,
  GMAIL_APP_PASSWORD,
} = process.env;

const apify = new ApifyClient({ token: APIFY_TOKEN });
const anthropic = new Anthropic({ apiKey: ANTHROPIC_KEY });
// claude-sonnet-4-20250514 reaches end-of-life June 15, 2026
const CLAUDE_MODEL = 'claude-sonnet-4-6';

// Helpers
const tenDaysAgoISO = () => {
  const d = new Date();
  d.setDate(d.getDate() - 10);
  return d.toISOString().split('T')[0];
};

const todayPretty = () => {
  return new Date().toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  });
};

const truncate = (str, n) => {
  if (!str) return '';
  return str.length > n ? str.slice(0, n) + '...' : str;
};

// ============================================================
// STEP 1 — SCRAPE (YouTube + Twitter + Instagram in parallel)
// ============================================================

async function scrapeYouTube() {
  console.log('  [YouTube] starting...');
  const input = {
    startUrls: [
      { url: 'https://www.youtube.com/@CNBCTelevision/videos' },
      { url: 'https://www.youtube.com/@DanMartell/videos' },
      { url: 'https://www.youtube.com/@lennyspodcast/videos' },
      { url: 'https://www.youtube.com/@futurepedia/videos' },
    ],
    maxResults: 15,
    maxResultsShorts: 0,
    maxResultStreams: 0,
    dateFilter: 'w',
  };
  const run = await apify.actor('streamers/youtube-scraper').call(input);
  const { items } = await apify.dataset(run.defaultDatasetId).listItems();
  const cutoff = new Date();
  cutoff.setDate(cutoff.getDate() - 10);
  const filtered = items
    .filter((v) => {
      if (!v.date) return true;
      return new Date(v.date) >= cutoff;
    })
    .map((v) => ({
      title: v.title || '',
      channel: v.channelName || v.channel || '',
      date: v.date || '',
      url: v.url || '',
      description: v.text || v.description || '',
    }));
  console.log(`  [YouTube] ${filtered.length} videos`);
  return filtered;
}

async function scrapeTwitter() {
  console.log('  [Twitter] starting...');
  if (!TWITTER_COOKIE) {
    console.log('  [Twitter] TWITTER_COOKIE missing in .env, skipping Twitter.');
    return [];
  }
  const searchTerms = [
    'AI announcement min_faves:500',
    'LLM release min_faves:300',
    'AI agents enterprise min_faves:200',
  ];
  const handles = [
    'sama',
    'karpathy',
    'demishassabis',
    'GaryMarcus',
    'AnthropicAI',
    'OpenAI',
    'GoogleDeepMind',
  ];
  const input = {
    searchTerms,
    twitterHandles: handles,
    maxItems: 30,
    sort: 'Latest',
    start: tenDaysAgoISO(),
    customMapFunction: '(object) => { return {...object} }',
  };
  if (TWITTER_COOKIE) {
    input.authCookies = [{ name: 'auth_token', value: TWITTER_COOKIE, domain: '.x.com' }];
  }
  try {
    const run = await apify.actor('apidojo/twitter-scraper-lite').call(input);
    const { items } = await apify.dataset(run.defaultDatasetId).listItems();
    const mapped = items.map((t) => ({
      author: t.author?.userName || t.author?.name || t.username || '',
      date: t.createdAt || t.created_at || '',
      text: t.text || t.fullText || '',
      url: t.url || t.twitterUrl || '',
      engagement:
        (t.likeCount || t.favorite_count || 0) +
        (t.retweetCount || t.retweet_count || 0) +
        (t.replyCount || t.reply_count || 0),
    }));
    console.log(`  [Twitter] ${mapped.length} tweets`);
    return mapped;
  } catch (err) {
    console.log(`  [Twitter] error: ${err.message}, skipping.`);
    return [];
  }
}

async function scrapeInstagram() {
  console.log('  [Instagram] starting...');
  const input = {
    username: ['evolvingai'],
    resultsType: 'posts',
    resultsLimit: 15,
  };
  try {
    const run = await apify.actor('apify/instagram-scraper').call(input);
    const { items } = await apify.dataset(run.defaultDatasetId).listItems();
    const mapped = items.map((p) => ({
      caption: p.caption || '',
      date: p.timestamp || '',
      hashtags: p.hashtags || [],
      likesCount: p.likesCount || 0,
      url: p.url || '',
    }));
    console.log(`  [Instagram] ${mapped.length} posts`);
    return mapped;
  } catch (err) {
    console.log(`  [Instagram] error: ${err.message}, skipping.`);
    return [];
  }
}

// ============================================================
// STEP 2 — AGGREGATE into one ≤8000 char text block
// ============================================================

function aggregate(youtube, twitter, instagram) {
  const sortByDate = (arr) =>
    [...arr].sort((a, b) => new Date(b.date || 0) - new Date(a.date || 0));
  const sortTweets = (arr) =>
    [...arr].sort(
      (a, b) =>
        (b.engagement || 0) - (a.engagement || 0) ||
        new Date(b.date || 0) - new Date(a.date || 0),
    );

  const yt = sortByDate(youtube);
  const tw = sortTweets(twitter);
  const ig = sortByDate(instagram);

  const buildBlock = (yLimit, tLimit, iLimit) => {
    let out = 'YOUTUBE:\n';
    yt.slice(0, yLimit).forEach((v) => {
      out += `${v.title} | ${v.channel} | ${v.date} | ${v.url}\n`;
      out += `${truncate(v.description, 300)}\n\n`;
    });
    out += '\nTWITTER:\n';
    tw.slice(0, tLimit).forEach((t) => {
      out += `@${t.author} | ${t.date} | ${truncate(t.text, 280)} | ${t.url}\n`;
    });
    out += '\nINSTAGRAM (@evolvingai):\n';
    ig.slice(0, iLimit).forEach((p) => {
      out += `${p.date} | ${truncate(p.caption, 200)} | ${p.likesCount} likes\n`;
    });
    return out;
  };

  let yLimit = yt.length;
  let tLimit = tw.length;
  let iLimit = ig.length;
  let block = buildBlock(yLimit, tLimit, iLimit);
  while (block.length > 8000 && (yLimit > 3 || tLimit > 3 || iLimit > 3)) {
    if (yLimit > 3) yLimit--;
    if (block.length > 8000 && tLimit > 3) tLimit--;
    if (block.length > 8000 && iLimit > 3) iLimit--;
    block = buildBlock(yLimit, tLimit, iLimit);
  }
  if (block.length > 8000) block = block.slice(0, 8000);
  return block;
}

// ============================================================
// STEP 3 — SCORE with Claude, pick top 3 stories
// ============================================================

async function scoreStories(aggregatedText, topN = 2) {
  const systemPrompt =
    `You are a news editor for @chatjerrpt, a TikTok account about AI strategy and business impact. Review the content and select the ${topN} best stories for TikTok posts. Score each on: news freshness, business relevance, and second-order potential (non-obvious downstream impact on companies or workers). Return ONLY a valid JSON array of the top ${topN} with fields: title, source, url, summary (2 sentences max), second_order_angle (the non-obvious take in one sentence). No extra text. No markdown. Just the JSON array.`;

  const callClaude = async (extraInstruction = '') => {
    const userMsg = extraInstruction
      ? `${extraInstruction}\n\n${aggregatedText}`
      : aggregatedText;
    const res = await anthropic.messages.create({
      model: CLAUDE_MODEL,
      max_tokens: 1000,
      system: systemPrompt,
      messages: [{ role: 'user', content: userMsg }],
    });
    return res.content[0].text.trim();
  };

  let raw = await callClaude();
  try {
    const cleaned = raw.replace(/^```json\s*/i, '').replace(/```$/, '').trim();
    return JSON.parse(cleaned);
  } catch (e) {
    console.log('  [Score] JSON parse failed, retrying...');
    raw = await callClaude(
      'Your previous response was not valid JSON. Return ONLY a JSON array, no markdown, no prose.',
    );
    const cleaned = raw.replace(/^```json\s*/i, '').replace(/```$/, '').trim();
    return JSON.parse(cleaned);
  }
}

// ============================================================
// STEP 4 — DRAFT 3 post packages
// ============================================================

async function draftPosts(stories) {
  const systemPrompt = `You are the content editor for @chatjerrpt on TikTok. Jerry is a UCLA Anderson MBA candidate with investment banking and strategic finance background, building an AI consulting practice called Clearstep.AI. Brand voice: sharp business analyst explaining things at a bar. Direct, specific, slightly skeptical of hype. Not corporate. Not academic.

HARD RULES — NEVER BREAK THESE:
- NEVER use em dashes. Use commas or short sentences instead
- NEVER use periods at end of bullet points
- NEVER write Let's dive in, That's it, In conclusion, or any AI-sounding opener or closer
- NEVER say 'let me know in the comments'
- Exactly 5 hashtags per post, no more, no less
- Use #Gemini not #GoogleAI when Google is relevant
- Default hashtags when unsure: #AIStrategy #FutureOfWork #BusinessTransformation #LearnAI #Gemini
- Captions: 150 to 200 words max, shorter is better
- Every claim needs a real number, name, or example attached to it
- Always name the specific source (Dan Martell's latest video, not 'a recent video')
- Second-order take must be genuinely non-obvious. Not the headline implication. The one level deeper that most people skip.

For each selected story produce exactly this structure, labeled clearly:

--- POST 1 ---

HEADLINE:
[8-15 words. Attention-grabbing. Use a number, contrarian angle, or Here's why/what frame]

CAPTION:
[Hook: 1-2 sentences that challenge an assumption or state a sharp insight. No filler opener.]

[Pick the most fitting label from: The insight / What this unlocks / The catch / Here's what matters]:
[2-3 sentences max]

[My take]:
[2-3 sentences. The second-order angle. What changes downstream, who wins, who loses.]

[Bottom line]:
[One punchy forward-looking prediction or question. Makes the reader think. Does not ask them to comment.]

#tag1 #tag2 #tag3 #tag4 #tag5

VOICEOVER SCRIPT (30-60 seconds spoken):
[Hook: one sentence that names the news and creates tension]
[What happened: 2-3 plain English sentences, no jargon, ~15 seconds]
[The real implication: 3-4 sentences on the second-order take, what most people miss, ~25 seconds]
[Close: one punchy prediction or question]
Write for how people talk out loud. Short sentences. No jargon.

GRAPHIC SLIDES (4 slides, bold and minimal like @evolvingai, dark backgrounds, one idea per slide):
Slide 1 [Hook]: HEADLINE (5-8 words) | Supporting line (1 sentence) | Visual: dark navy background, large bold white text
Slide 2 [Context]: HEADLINE | Supporting line with specific stat or name | Visual: dark background, highlight the number
Slide 3 [The insight]: HEADLINE | The non-obvious implication in one sentence | Visual: accent color on key phrase
Slide 4 [Close]: HEADLINE (punchy, 4-6 words) | Visual: minimal, bold typography, no clutter

--- POST 2 --- [same structure]`;

  const userMsg = `Here are today's selected stories (${stories.length}): ${JSON.stringify(stories, null, 2)}\nDraft all post packages now.`;

  const res = await anthropic.messages.create({
    model: CLAUDE_MODEL,
    max_tokens: 3000,
    system: systemPrompt,
    messages: [{ role: 'user', content: userMsg }],
  });
  return res.content[0].text;
}

// ============================================================
// STEP 4.5 — SELF-REVIEW: check drafts against the hard content
// rules, have Claude revise until they pass (max 3 rounds)
// ============================================================

// Mechanical checks for rules a regex can catch. Claude handles
// the judgment calls (voice, source naming, second-order depth).
function validateDrafts(text, expectedPosts = 2) {
  const violations = [];
  if (text.includes('—')) violations.push('Contains an em dash, hard rule says never use them');
  const lower = text.toLowerCase();
  const banned = ["let's dive in", "that's it", 'in conclusion', 'let me know in the comments'];
  banned.forEach((p) => {
    if (lower.includes(p)) violations.push(`Contains banned phrase: "${p}"`);
  });
  if (/#GoogleAI\b/i.test(text)) violations.push('Uses #GoogleAI, must use #Gemini instead');
  const posts = text.split(/--- POST \d+ ---/).slice(1);
  if (posts.length !== expectedPosts) violations.push(`Expected ${expectedPosts} posts, found ${posts.length}`);
  posts.forEach((p, i) => {
    const tagLine = p.split('\n').find((l) => l.trim().startsWith('#')) || '';
    const count = (tagLine.match(/#[A-Za-z0-9_]+/g) || []).length;
    if (count !== 5) violations.push(`Post ${i + 1}: hashtag line has ${count} hashtags, rule requires exactly 5`);
  });
  return violations;
}

async function selfReviewDrafts(draftText) {
  const reviewSystem = `You are the quality reviewer for @chatjerrpt TikTok drafts. Check the drafts against these HARD RULES:
- No em dashes anywhere
- No periods at end of bullet points
- No AI-sounding openers or closers (Let's dive in, That's it, In conclusion)
- Never say 'let me know in the comments'
- Exactly 5 hashtags per post
- #Gemini not #GoogleAI
- Captions 150 to 200 words max
- Every claim has a real number, name, or example
- Sources named specifically
- Second-order take is genuinely non-obvious, one level deeper than the headline implication
- Voice: sharp business analyst at a bar. Direct, specific, slightly skeptical. Not corporate, not academic

If the drafts fully comply with every rule, reply with exactly: PASS
Otherwise return the COMPLETE corrected drafts, all posts in full with the same structure, fixing only what violates the rules. No commentary, no preamble, just PASS or the full corrected text.`;

  let current = draftText;
  for (let round = 1; round <= 3; round++) {
    const violations = validateDrafts(current);
    console.log(
      `  [Review] round ${round}: ${violations.length === 0 ? 'mechanical checks clean' : violations.join('; ')}`,
    );
    const userMsg =
      (violations.length
        ? `Automated checks found these violations, fix them along with anything else you catch:\n- ${violations.join('\n- ')}\n\n`
        : '') + `DRAFTS:\n${current}`;
    const res = await anthropic.messages.create({
      model: CLAUDE_MODEL,
      max_tokens: 3000,
      system: reviewSystem,
      messages: [{ role: 'user', content: userMsg }],
    });
    const out = res.content[0].text.trim();
    if (out === 'PASS' && violations.length === 0) {
      console.log(`  [Review] passed on round ${round}`);
      return current;
    }
    if (out !== 'PASS') current = out;
  }
  const remaining = validateDrafts(current);
  if (remaining.length) {
    console.log(`  [Review] WARNING: still failing after 3 rounds: ${remaining.join('; ')}`);
  } else {
    console.log('  [Review] passed after revisions');
  }
  return current;
}

// ============================================================
// STEP 5 — EMAIL DELIVERY via Gmail SMTP
// ============================================================

function makeTransport() {
  return nodemailer.createTransport({
    service: 'gmail',
    auth: {
      user: GMAIL_USER,
      pass: GMAIL_APP_PASSWORD,
    },
  });
}

async function sendEmail({ subject, body }) {
  const transport = makeTransport();
  await transport.sendMail({
    from: GMAIL_USER,
    to: EMAIL_TO,
    subject,
    text: body,
  });
}

async function sendPostsEmail(stories, draftText) {
  const sourcesHeader =
    'SOURCES FOR TODAY\n' +
    stories
      .map((s, i) => `${i + 1}. ${s.title} | ${s.source} | ${s.url}`)
      .join('\n') +
    '\n\n========================================\n\n';
  const body = sourcesHeader + draftText;
  await sendEmail({
    subject: `Your TikTok Posts — ${todayPretty()}`,
    body,
  });
}

async function sendErrorEmail(step, err) {
  try {
    await sendEmail({
      subject: `TikTok Pipeline FAILED at ${step} — ${todayPretty()}`,
      body: `Pipeline failed at step: ${step}\n\nError: ${err.message}\n\nStack:\n${err.stack}`,
    });
  } catch (e) {
    console.error('Could not send error email:', e.message);
  }
}

// ============================================================
// PIPELINE — runs end-to-end
// ============================================================

async function runPipeline() {
  console.log('\nPipeline starting...');
  let step = 'init';
  try {
    step = 'scrape';
    console.log('Step 1: scraping...');
    const [youtube, twitter, instagram] = await Promise.all([
      scrapeYouTube(),
      scrapeTwitter(),
      scrapeInstagram(),
    ]);

    step = 'aggregate';
    console.log('Step 2: aggregating...');
    const aggregated = aggregate(youtube, twitter, instagram);
    console.log(`  Aggregated block: ${aggregated.length} chars`);

    step = 'score';
    console.log('Step 3: scoring with Claude (top 2)...');
    const stories = await scoreStories(aggregated, 2);
    console.log(`  Got ${stories.length} stories`);

    step = 'draft';
    console.log('Step 4: drafting post packages...');
    let draftText = await draftPosts(stories);
    console.log(`  Drafted (${draftText.length} chars)`);

    step = 'review';
    console.log('Step 4.5: self-review against content rules...');
    draftText = await selfReviewDrafts(draftText);
    console.log('\n========== DRAFT PREVIEW ==========\n');
    console.log(draftText);
    console.log('\n========== END PREVIEW ==========\n');

    step = 'email';
    console.log('Step 5: sending email...');
    await sendPostsEmail(stories, draftText);

    console.log(`Done. Posts sent to ${EMAIL_TO}.`);
  } catch (err) {
    console.error(`Pipeline failed at step "${step}":`, err.message);
    console.error(err.stack);
    await sendErrorEmail(step, err);
  }
}

// ============================================================
// STEP 6 — SCHEDULER (7:00 AM daily)
// ============================================================

// Scheduler only arms when run directly (node index.js), so the
// pipeline functions can be required by test scripts without
// kicking off a run.
if (require.main === module) {
  cron.schedule('0 7 * * *', () => {
    runPipeline();
  });

  console.log('Scheduler armed: pipeline will run every day at 7:00 AM.');
  console.log('Running once now as a test...\n');
  runPipeline();
}

module.exports = {
  aggregate,
  scoreStories,
  draftPosts,
  validateDrafts,
  selfReviewDrafts,
  runPipeline,
};
