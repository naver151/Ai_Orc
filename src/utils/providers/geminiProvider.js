// TODO: 파트너가 API 키 및 구현 추가
// 참고: https://ai.google.dev/api/generate-content

export async function callGemini(systemPrompt, userMessage) {
  // const apiKey = import.meta.env.VITE_GEMINI_API_KEY
  // const model  = 'gemini-1.5-flash'
  // const url = `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent?key=${apiKey}`
  //
  // const response = await fetch(url, {
  //   method: 'POST',
  //   headers: { 'Content-Type': 'application/json' },
  //   body: JSON.stringify({
  //     system_instruction: { parts: [{ text: systemPrompt }] },
  //     contents: [{ parts: [{ text: userMessage }] }],
  //     generationConfig: { maxOutputTokens: 1024 },
  //   }),
  // })
  // const data = await response.json()
  // return data.candidates[0].content.parts[0].text

  throw new Error('geminiProvider: API 구현을 추가해주세요')
}
