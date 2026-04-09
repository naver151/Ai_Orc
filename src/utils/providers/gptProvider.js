// TODO: 파트너가 API 키 및 구현 추가
// 참고: https://platform.openai.com/docs/api-reference/chat

export async function callGPT(systemPrompt, userMessage) {
  // const response = await fetch('https://api.openai.com/v1/chat/completions', {
  //   method: 'POST',
  //   headers: {
  //     'Content-Type': 'application/json',
  //     'Authorization': 'Bearer ' + import.meta.env.VITE_OPENAI_API_KEY,
  //   },
  //   body: JSON.stringify({
  //     model: 'gpt-4o',
  //     messages: [
  //       { role: 'system', content: systemPrompt },
  //       { role: 'user',   content: userMessage  },
  //     ],
  //     max_tokens: 1024,
  //   }),
  // })
  // const data = await response.json()
  // return data.choices[0].message.content

  throw new Error('gptProvider: API 구현을 추가해주세요')
}
