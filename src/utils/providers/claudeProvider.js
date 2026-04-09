// TODO: 파트너가 API 키 및 구현 추가
// 참고: https://docs.anthropic.com/en/api/messages

export async function callClaude(systemPrompt, userMessage) {
  // const response = await fetch('https://api.anthropic.com/v1/messages', {
  //   method: 'POST',
  //   headers: {
  //     'Content-Type': 'application/json',
  //     'x-api-key': import.meta.env.VITE_ANTHROPIC_API_KEY,
  //     'anthropic-version': '2023-06-01',
  //   },
  //   body: JSON.stringify({
  //     model: 'claude-sonnet-4-20250514',
  //     max_tokens: 1024,
  //     system: systemPrompt,
  //     messages: [{ role: 'user', content: userMessage }],
  //   }),
  // })
  // const data = await response.json()
  // return data.content[0].text

  throw new Error('claudeProvider: API 구현을 추가해주세요')
}
