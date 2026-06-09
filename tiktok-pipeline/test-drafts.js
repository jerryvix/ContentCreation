// Dev utility: runs Steps 3 -> 4 -> 4.5 of the pipeline with a
// pre-aggregated news block, skipping the Apify scrape and SMTP
// email (both blocked in the remote sandbox). Writes the reviewed
// drafts to drafts_output.txt.

const fs = require('fs');
const { scoreStories, draftPosts, selfReviewDrafts, validateDrafts } = require('./index.js');

const aggregated = `
NEWS (week of June 1-9, 2026):

Anthropic confidentially filed a draft S-1 with the SEC on June 1, 2026. Revenue run-rate hit roughly $47 billion in May 2026, up from about $10 billion a year earlier, roughly 5x annual growth. | TechCrunch | https://techcrunch.com/2026/06/08/following-anthropic-openai-files-confidentially-for-ipo/

OpenAI filed confidentially for an IPO on June 8, 2026, a little more than a week after Anthropic filed. | TechCrunch | https://techcrunch.com/2026/06/08/following-anthropic-openai-files-confidentially-for-ipo/

Apple WWDC 2026: Apple partnered with Google to make Gemini the default model powering the new Siri AI assistant. iOS 27 / macOS 27 add an Extensions system in the App Store letting users pick third-party AI (ChatGPT, Claude, Gemini) as the default for Apple Intelligence features like Writing Tools and Image Playground. Apple's LanguageModel protocol is a public Swift interface that Anthropic and Google currently implement, so apps can swap AI providers without code changes. Reaches 2 billion plus active Apple devices. | Tom's Guide / Digital Trends / TechTimes | https://www.tomsguide.com/news/live/wwdc-2026-live-news-updates

OpenAI launched six role-specific Codex business plugins on June 2, 2026: data analytics, creative production, sales, product design, public equity investing, and investment banking. The investment banking plugin prepares pitch materials, analyzes comparable companies and transactions, and turns diligence into recommendations. Codex now has 5 million plus weekly active users, up 6x since the February desktop app launch. Non-developers (analysts, marketers, bankers) are about 20% of users and growing 3x faster than developers. New Sites feature outputs work as hosted interactive websites. | TechCrunch / OpenAI | https://techcrunch.com/2026/06/02/openai-launches-new-codex-tools-for-white-collar-work/

Microsoft Build 2026: Microsoft Foundry model catalog now contains 11,000+ models including frontier closed-weight models from OpenAI, Anthropic, and Google. | CNBC | https://www.cnbc.com/2026/06/01/microsoft-and-google-take-on-anthropic-and-openai-in-ai-coding-models.html
`;

(async () => {
  console.log('Step 3: scoring with Claude...');
  const stories = await scoreStories(aggregated);
  console.log(`  Got ${stories.length} stories:`);
  stories.forEach((s, i) => console.log(`  ${i + 1}. ${s.title}`));

  console.log('Step 4: drafting 3 post packages...');
  let draftText = await draftPosts(stories);
  console.log(`  Drafted (${draftText.length} chars)`);

  console.log('Step 4.5: self-review against content rules...');
  draftText = await selfReviewDrafts(draftText);

  const finalViolations = validateDrafts(draftText);
  console.log(
    finalViolations.length
      ? `FINAL CHECK FAILED: ${finalViolations.join('; ')}`
      : 'FINAL CHECK: all mechanical rules pass',
  );

  const sourcesHeader =
    'SOURCES FOR TODAY\n' +
    stories.map((s, i) => `${i + 1}. ${s.title} | ${s.source} | ${s.url}`).join('\n') +
    '\n\n========================================\n\n';
  fs.writeFileSync('drafts_output.txt', sourcesHeader + draftText);
  console.log('Wrote drafts_output.txt');
})().catch((e) => {
  console.error('FAILED:', e.message);
  process.exit(1);
});
