'''agent主体'''
from langchain.agents import create_agent

from app.modelFactory.factory import chat_model
from app.utils.prompt_loader import load_system_prompt
from app.service.agent.tools.agent_tools import rag_summarize
from app.service.agent.tools.middleware import monitor_tool,log_before_model


class ReActAgent:
    def __init__(self):
        self.agent = create_agent(
            model = chat_model,
            system_prompt=load_system_prompt(),
            tools=[rag_summarize],
            middleware=[monitor_tool,log_before_model],
        )

    def execute_stream(self,query:str):
        """流式输出"""
        input_dict = {
            "messages":[
                {"role":"user","content":query},
            ]
        }

        for chunk in self.agent.stream(input_dict,stream_mode="values"):
            latest_message = chunk["messages"][-1]
            if latest_message.content:
                yield latest_message.content.strip() + "\n"

# if __name__ == '__main__':
#     agent = ReActAgent()

#     for chunk in agent.execute_stream("给我讲讲行为规范与保密义务"):
#         print(chunk,end="",flush=True)
