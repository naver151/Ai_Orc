# API 요구사항 및 명세

## 1. 계산 기록 및 데이터 구조 요구사항 정의

### 데이터 구조
계산기의 계산 기록은 다음의 사항들을 포함하는 데이터로 구성됩니다:
- **operation** (문자열): 수행된 연산의 종류 (예: 덧셈, 뺄셈, 곱셈, 나눗셈 등)
- **operands** (숫자 배열): 연산에 사용된 피연산자 (리스트 형태)
- **result** (숫자): 연산의 결과

이 데이터는 In-Memory 데이터베이스 구조로 관리되며, 추후 영구 저장 기능을 추가할 수 있습니다.

### 기능 요구사항
1. **새로운 계산 기록 저장**: 사용자가 수행한 계산의 기록을 서버에 저장.
2. **계산 기록 조회**: 저장된 모든 계산 기록을 사용자에게 반환.

## 2. API 명세

### 엔드포인트 1: `/calculate`
- **메서드**: POST
- **설명**: 새로운 계산 기록을 추가합니다.
- **Request Body**:
  ```json
  {
    "operation": "string",
    "operands": [float, ...],
    "result": float
  }
  ```
- **Response**:
  - **성공 시 (201)**: 저장된 계산 기록을 반환.
  ```json
  {
    "operation": "string",
    "operands": [float, ...],
    "result": float
  }
  ```

### 엔드포인트 2: `/history`
- **메서드**: GET
- **설명**: 모든 계산 기록을 조회합니다.
- **Response**:
  - **성공 시 (200)**: 계산 기록 배열을 반환.
  ```json
  [
    {
      "operation": "string",
      "operands": [float, ...],
      "result": float
    },
    ...
  ]
  ```

### 엔드포인트 3: `/`
- **메서드**: GET
- **설명**: 기본 정보를 반환합니다.
- **Response**:
  ```json
  {
    "message": "Welcome to the calculator API!"
  }
  ```