from pydantic import BaseModel, Field, model_validator


class LinkInput(BaseModel):
    text: str = Field(min_length=1, max_length=10000)


class Sentence(BaseModel):
    id: str
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    text: str = Field(max_length=10000)

    @model_validator(mode='after')
    def time_order(self):
        if self.end <= self.start:
            raise ValueError('结束时间必须大于开始时间')
        return self


class Shot(Sentence):
    description: str = Field(default='', max_length=10000)
    role: str = Field(default='', max_length=10000)
    rhythm: str = Field(default='', max_length=10000)
    uncertain: bool = False


class Overview(BaseModel):
    topic: str = Field(default='', max_length=10000)
    audience: str = Field(default='', max_length=10000)
    hook: str = Field(default='', max_length=10000)
    structure: str = Field(default='', max_length=20000)
    rhythm: str = Field(default='', max_length=10000)
    observations: str = Field(default='', max_length=20000)
    takeaways: str = Field(default='', max_length=20000)
    uncertainties: str = Field(default='', max_length=10000)


class EditInput(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    overview: Overview
    transcript: list[Sentence] = Field(max_length=2000)
    shots: list[Shot] = Field(max_length=2000)


